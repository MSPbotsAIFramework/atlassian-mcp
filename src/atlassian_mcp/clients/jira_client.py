"""Jira Platform REST v3 client -- the 7 endpoints behind the Jira tools.

Uses POST /rest/api/3/search/jql (the current "enhanced" search), not the
deprecated GET/POST /rest/api/3/search -- see PRD-21297 tech design §
Option analysis.
"""

from __future__ import annotations

from typing import Any

from atlassian_mcp.clients.base import build_client, raise_for_status, request_with_retry
from atlassian_mcp.errors import AtlassianMcpError
from atlassian_mcp.middleware import AtlassianCredentials

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _capped_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


async def search_issues(
    creds: AtlassianCredentials,
    jql: str,
    *,
    limit: int = DEFAULT_LIMIT,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    body = {
        "jql": jql,
        "maxResults": _capped_limit(limit),
        "fields": fields or ["summary", "status", "assignee", "updated"],
    }
    async with build_client(creds) as client:
        resp = await request_with_retry(client, "POST", "/rest/api/3/search/jql", json=body)
        raise_for_status(resp)
        payload = resp.json_body or {}

    issues = []
    for raw in payload.get("issues", []):
        fields_obj = raw.get("fields", {})
        assignee = fields_obj.get("assignee") or {}
        status = fields_obj.get("status") or {}
        issues.append(
            {
                "key": raw.get("key"),
                "summary": fields_obj.get("summary"),
                "status": status.get("name"),
                "assignee": assignee.get("emailAddress") or assignee.get("displayName"),
                "updated": fields_obj.get("updated"),
            }
        )
    return {"issues": issues, "next_page_token": payload.get("nextPageToken")}


async def get_issue(creds: AtlassianCredentials, issue_key: str) -> dict[str, Any]:
    async with build_client(creds) as client:
        resp = await request_with_retry(
            client,
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            params={"fields": "summary,status,assignee,description,comment"},
        )
        raise_for_status(resp, not_found_message=f"issue {issue_key} not found")
        raw = resp.json_body or {}

    fields_obj = raw.get("fields", {})
    assignee = fields_obj.get("assignee") or {}
    status = fields_obj.get("status") or {}
    comment_obj = fields_obj.get("comment") or {}
    return {
        "key": raw.get("key"),
        "summary": fields_obj.get("summary"),
        "status": status.get("name"),
        "assignee": assignee.get("emailAddress") or assignee.get("displayName"),
        "description": fields_obj.get("description"),
        "comment_count": comment_obj.get("total", 0),
    }


async def create_issue(
    creds: AtlassianCredentials,
    *,
    project_key: str,
    summary: str,
    issue_type: str,
    description: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        }

    async with build_client(creds) as client:
        resp = await request_with_retry(client, "POST", "/rest/api/3/issue", json={"fields": fields})
        if resp.status_code == 400:
            raise AtlassianMcpError("invalid_argument", resp.text[:500], retryable=False)
        raise_for_status(resp)
        raw = resp.json_body or {}

    key = raw.get("key")
    return {"key": key, "url": f"{creds.site}/browse/{key}"}


async def update_issue(creds: AtlassianCredentials, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Only the keys present in `fields` are sent -- a partial PUT."""
    allowed = {"summary", "description", "assignee"}
    unsupported = [name for name in fields if name not in allowed]
    if unsupported:
        raise AtlassianMcpError(
            "invalid_argument",
            f"unsupported field(s): {', '.join(unsupported)}; allowed: {', '.join(sorted(allowed))}",
            retryable=False,
        )

    payload_fields: dict[str, Any] = {}
    if "summary" in fields:
        payload_fields["summary"] = fields["summary"]
    if "description" in fields:
        payload_fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": fields["description"]}]}],
        }
    if "assignee" in fields:
        payload_fields["assignee"] = {"accountId": fields["assignee"]} if fields["assignee"] else None

    async with build_client(creds) as client:
        resp = await request_with_retry(client, "PUT", f"/rest/api/3/issue/{issue_key}", json={"fields": payload_fields})
        if resp.status_code == 400:
            raise AtlassianMcpError("invalid_argument", resp.text[:500], retryable=False)
        raise_for_status(resp, not_found_message=f"issue {issue_key} not found")

    return {"updated": True}


async def transition_issue(creds: AtlassianCredentials, issue_key: str, target_status: str) -> dict[str, Any]:
    async with build_client(creds) as client:
        list_resp = await request_with_retry(client, "GET", f"/rest/api/3/issue/{issue_key}/transitions")
        raise_for_status(list_resp, not_found_message=f"issue {issue_key} not found")
        transitions = (list_resp.json_body or {}).get("transitions", [])

        match = next((t for t in transitions if t.get("name", "").lower() == target_status.lower()), None)
        if match is None:
            available = [t.get("name") for t in transitions]
            raise AtlassianMcpError(
                "invalid_argument",
                f"'{target_status}' is not a valid transition from the current status; available: {', '.join(available)}",
                retryable=False,
            )

        post_resp = await request_with_retry(
            client,
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        raise_for_status(post_resp)

    return {"transitioned_to": match["name"]}


async def add_comment(creds: AtlassianCredentials, issue_key: str, body: str) -> dict[str, Any]:
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
        }
    }
    async with build_client(creds) as client:
        resp = await request_with_retry(client, "POST", f"/rest/api/3/issue/{issue_key}/comment", json=payload)
        raise_for_status(resp, not_found_message=f"issue {issue_key} not found")
        raw = resp.json_body or {}

    return {"comment_id": raw.get("id")}


async def list_projects(creds: AtlassianCredentials, *, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    async with build_client(creds) as client:
        resp = await request_with_retry(
            client,
            "GET",
            "/rest/api/3/project/search",
            params={"maxResults": _capped_limit(limit)},
        )
        raise_for_status(resp)
        payload = resp.json_body or {}

    projects = [
        {"key": p.get("key"), "name": p.get("name"), "project_type": p.get("projectTypeKey")}
        for p in payload.get("values", [])
    ]
    return {"projects": projects}
