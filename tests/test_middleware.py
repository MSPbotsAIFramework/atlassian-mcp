"""TC18 (AC13: missing-header 401) and TC19 (AC14: concurrent tenant isolation)."""

from __future__ import annotations

import asyncio
import json

import respx
from httpx import Response
from starlette.testclient import TestClient

from atlassian_mcp.middleware import AtlassianCredentials, bind_credentials
from atlassian_mcp.server import app
from atlassian_mcp.tools.jira_tools import atlassian_jira_get_issue


# --- TC18 / AC13 -----------------------------------------------------------


@respx.mock(assert_all_mocked=True)
def test_missing_credential_header_returns_401_with_required_list():
    """No Atlassian route is registered with respx -- any outbound call would
    raise respx.AllMockedAssertionError, so a passing test proves none was made."""
    client = TestClient(app)
    response = client.post(
        "/mcp",
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    for header in ("X-Atlassian-Site", "X-Atlassian-Email", "X-Atlassian-Api-Token"):
        assert header in body["error"]["message"]


@respx.mock(assert_all_mocked=True)
def test_missing_one_credential_header_lists_only_that_header():
    client = TestClient(app)
    response = client.post(
        "/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-Atlassian-Site": "https://acme.atlassian.net",
            "X-Atlassian-Email": "jane@acme.com",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["message"] == "missing required headers: X-Atlassian-Api-Token"


# --- TC19 / AC14 -------------------------------------------------------------


async def test_credentials_are_not_shared_across_concurrent_requests():
    creds_a = AtlassianCredentials(site="https://tenant-a.atlassian.net", email="a@a.com", api_token="tok-a")
    creds_b = AtlassianCredentials(site="https://tenant-b.atlassian.net", email="b@b.com", api_token="tok-b")

    with respx.mock(assert_all_mocked=True) as mock_router:
        mock_router.get(f"{creds_a.site}/rest/api/3/issue/ISSUE-1").mock(
            return_value=Response(200, json={"key": "ISSUE-1", "fields": {"summary": "tenant A's issue"}})
        )
        mock_router.get(f"{creds_b.site}/rest/api/3/issue/ISSUE-1").mock(
            return_value=Response(200, json={"key": "ISSUE-1", "fields": {"summary": "tenant B's issue"}})
        )

        async def call_as(creds: AtlassianCredentials) -> dict:
            async with bind_credentials(creds):
                # Yield control so the two coroutines genuinely interleave
                # instead of one running to completion before the other starts.
                await asyncio.sleep(0)
                raw = await atlassian_jira_get_issue(issue_key="ISSUE-1")
                return json.loads(raw)

        result_a, result_b = await asyncio.gather(call_as(creds_a), call_as(creds_b))

    assert result_a["summary"] == "tenant A's issue"
    assert result_b["summary"] == "tenant B's issue"
