"""Shared HTTP plumbing: timeouts, bounded retry with backoff, Basic auth.

One httpx.AsyncClient is built per request (not a process-wide singleton),
since the base URL and Basic-auth credentials are request-scoped (the
tenant's own Atlassian site + API token) -- see SOP §3.3/§3.4 on request
isolation. 5s connect / 30s read timeout and bounded 429/5xx retry honoring
Retry-After are from PRD-21297 tech design § Non-functional.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

import httpx

from atlassian_mcp.errors import AtlassianMcpError, map_http_status
from atlassian_mcp.middleware import AtlassianCredentials

CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 30.0
MAX_RETRIES = 3
MAX_TOTAL_WAIT_S = 90.0  # keeps a single tool call well under the 120s cap (SOP §5)


@dataclass(frozen=True, slots=True)
class UpstreamResponse:
    status_code: int
    json_body: dict | list | None
    text: str


def _basic_auth_header(email: str, api_token: str) -> str:
    raw = f"{email}:{api_token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def build_client(creds: AtlassianCredentials, *, base_path: str = "") -> httpx.AsyncClient:
    """One client per request/call site, scoped to this request's tenant."""
    return httpx.AsyncClient(
        base_url=creds.site + base_path,
        headers={
            "Authorization": _basic_auth_header(creds.email, creds.api_token),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S, write=READ_TIMEOUT_S, pool=READ_TIMEOUT_S),
    )


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> UpstreamResponse:
    """Issue one call with bounded retry on 429/5xx, honoring Retry-After.

    Raises AtlassianMcpError (network failure -> upstream_error) rather than
    letting httpx exceptions escape -- tool code never has to catch httpx
    errors itself.
    """
    total_waited = 0.0
    last_response: httpx.Response | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise AtlassianMcpError("upstream_error", f"Atlassian request timed out: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise AtlassianMcpError("upstream_error", f"Atlassian request failed: {exc}", retryable=True) from exc

        last_response = response
        if response.status_code not in (429, 500, 502, 503, 504):
            break
        if attempt == MAX_RETRIES:
            break

        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2.0 ** attempt, 10.0)
        if total_waited + delay > MAX_TOTAL_WAIT_S:
            break
        await asyncio.sleep(delay)
        total_waited += delay

    assert last_response is not None
    try:
        body = last_response.json() if last_response.content else None
    except ValueError:
        body = None
    return UpstreamResponse(status_code=last_response.status_code, json_body=body, text=last_response.text)


def raise_for_status(resp: UpstreamResponse, *, not_found_message: str | None = None) -> None:
    if 200 <= resp.status_code < 300:
        return
    if resp.status_code == 404 and not_found_message:
        raise map_http_status(404, upstream_message=not_found_message)
    message = None
    if isinstance(resp.json_body, dict):
        message = resp.json_body.get("message") or str(resp.json_body.get("errorMessages") or resp.json_body.get("errors") or "")
    raise map_http_status(resp.status_code, upstream_message=message or resp.text[:500])
