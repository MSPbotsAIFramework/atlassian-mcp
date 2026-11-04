"""Confluence REST v2 client -- the 5 endpoints behind the Confluence tools.

Search still goes through the older CQL search endpoint
(/wiki/rest/api/search) because Confluence v2's own page-listing endpoints
do not yet expose a general CQL filter -- see PRD-21297 tech design §
Data & API contract and § Risks ("Confluence v1 vs v2 API drift").
Everything else (get/create/update page, list spaces) uses v2.
"""

from __future__ import annotations

import re
from typing import Any

from atlassian_mcp.clients.base import build_client, raise_for_status, request_with_retry
from atlassian_mcp.errors import AtlassianMcpError
from atlassian_mcp.middleware import AtlassianCredentials

DEFAULT_LIMIT = 25
MAX_LIMIT = 100

_TAG_RE = re.compile(r"<[^>]+>")


def _capped_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _plain_text(storage_html: str) -> str:
    """Best-effort plain-text extract from Confluence storage-format body."""
    return _TAG_RE.sub("", storage_html or "").strip()


async def search_pages(creds: AtlassianCredentials, cql: str, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    async with build_client(creds) as client:
        resp = await request_with_retry(
            client,
            "GET",
            "/wiki/rest/api/search",
            params={"cql": cql, "limit": _capped_limit(limit)},
        )
        raise_for_status(resp)
        payload = resp.json_body or {}

    pages = []
    for raw in payload.get("results", []):
        content = raw.get("content", raw)
        space = content.get("space", {}) if isinstance(content, dict) else {}
        pages.append(
            {
                "id": content.get("id"),
                "title": content.get("title"),
                "space_key": space.get("key"),
                "url": creds.site + (raw.get("url") or ""),
            }
        )
    return {"pages": pages}


async def get_page(creds: AtlassianCredentials, page_id: str) -> dict[str, Any]:
    async with build_client(creds) as client:
        resp = await request_with_retry(
            client,
            "GET",
            f"/wiki/api/v2/pages/{page_id}",
            params={"body-format": "storage"},
        )
        raise_for_status(resp, not_found_message=f"page {page_id} not found")
        raw = resp.json_body or {}

    body = (raw.get("body") or {}).get("storage", {}).get("value", "")
    return {
        "id": raw.get("id"),
        "title": raw.get("title"),
        "space": raw.get("spaceId"),
        "body": _plain_text(body),
        "version": (raw.get("version") or {}).get("number"),
    }


async def _resolve_space_id(creds: AtlassianCredentials, space_key: str) -> str:
    async with build_client(creds) as client:
        resp = await request_with_retry(client, "GET", "/wiki/api/v2/spaces", params={"keys": space_key})
        raise_for_status(resp)
        results = (resp.json_body or {}).get("results", [])

    if not results:
        raise AtlassianMcpError("not_found", f"space '{space_key}' not found", retryable=False)
    return results[0]["id"]


async def create_page(
    creds: AtlassianCredentials,
    *,
    space_key: str,
    title: str,
    body_html: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    space_id = await _resolve_space_id(creds, space_key)
    payload = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "parentId": parent_id,
        "body": {"representation": "storage", "value": body_html},
    }
    async with build_client(creds) as client:
        resp = await request_with_retry(client, "POST", "/wiki/api/v2/pages", json=payload)
        if resp.status_code == 400:
            message = None
            if isinstance(resp.json_body, dict):
                errors = resp.json_body.get("errors") or []
                message = errors[0].get("title") if errors else None
            raise AtlassianMcpError("invalid_argument", message or f"duplicate title '{title}' in space '{space_key}'", retryable=False)
        raise_for_status(resp)
        raw = resp.json_body or {}

    page_id = raw.get("id")
    return {"id": page_id, "title": raw.get("title"), "url": f"{creds.site}/wiki/spaces/{space_key}/pages/{page_id}"}


async def update_page(
    creds: AtlassianCredentials,
    *,
    page_id: str,
    body_html: str,
    current_version: int,
) -> dict[str, Any]:
    async with build_client(creds) as client:
        get_resp = await request_with_retry(client, "GET", f"/wiki/api/v2/pages/{page_id}")
        raise_for_status(get_resp, not_found_message=f"page {page_id} not found")
        existing = get_resp.json_body or {}

        payload = {
            "id": page_id,
            "status": "current",
            "title": existing.get("title"),
            "body": {"representation": "storage", "value": body_html},
            "version": {"number": current_version + 1, "message": "Updated via MSPbots Agent platform"},
        }
        resp = await request_with_retry(client, "PUT", f"/wiki/api/v2/pages/{page_id}", json=payload)
        if resp.status_code == 409:
            raise AtlassianMcpError(
                "invalid_argument",
                f"version conflict: page {page_id} has moved past version {current_version}; reload and retry",
                retryable=False,
            )
        raise_for_status(resp)
        raw = resp.json_body or {}

    return {"version": (raw.get("version") or {}).get("number")}


async def list_spaces(creds: AtlassianCredentials, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    async with build_client(creds) as client:
        resp = await request_with_retry(client, "GET", "/wiki/api/v2/spaces", params={"limit": _capped_limit(limit)})
        raise_for_status(resp)
        payload = resp.json_body or {}

    spaces = [{"key": s.get("key"), "name": s.get("name")} for s in payload.get("results", [])]
    return {"spaces": spaces}
