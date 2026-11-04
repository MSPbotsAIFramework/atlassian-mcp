"""Auto test cases TC1, TC3, TC5, TC7, TC8, TC10-TC14, TC16, TC17 (docs/tickets/PRD-21297.ac.json).

Each test mocks the Atlassian HTTP response with respx -- no network, no
real vendor account needed (SOP "no test account still publishes to INT
as usual"). Manual-only cases (TC2, TC4, TC6, TC9, TC15) are not here; see
the ac.json `manual` entries.
"""

from __future__ import annotations

import json

import respx
from httpx import Response

from atlassian_mcp.middleware import AtlassianCredentials
from atlassian_mcp.server import mcp
from atlassian_mcp.tools.confluence_tools import (
    atlassian_confluence_create_page,
    atlassian_confluence_get_page,
    atlassian_confluence_list_spaces,
    atlassian_confluence_search_pages,
    atlassian_confluence_update_page,
)
from atlassian_mcp.tools.jira_tools import (
    atlassian_jira_add_comment,
    atlassian_jira_create_issue,
    atlassian_jira_get_issue,
    atlassian_jira_list_projects,
    atlassian_jira_search_issues,
    atlassian_jira_transition_issue,
    atlassian_jira_update_issue,
)

SITE = "https://acme.atlassian.net"


def _err(resp_text: str) -> dict:
    return json.loads(resp_text)


# --- tools/list snapshot: 12 tools, expected names -------------------------


async def test_tools_list_snapshot_has_12_tools_with_expected_names():
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(
        [
            "atlassian_jira_search_issues",
            "atlassian_jira_get_issue",
            "atlassian_jira_create_issue",
            "atlassian_jira_update_issue",
            "atlassian_jira_transition_issue",
            "atlassian_jira_add_comment",
            "atlassian_jira_list_projects",
            "atlassian_confluence_search_pages",
            "atlassian_confluence_get_page",
            "atlassian_confluence_create_page",
            "atlassian_confluence_update_page",
            "atlassian_confluence_list_spaces",
        ]
    )
    for t in tools:
        first_line = (t.description or "").splitlines()[0]
        assert len(t.description or "") <= 500, t.name
        assert len(first_line) <= 100, t.name


# --- TC1 / AC1 ---------------------------------------------------------


@respx.mock
async def test_jira_search_issues_builds_jql_search_request(bound_creds: AtlassianCredentials):
    route = respx.post(f"{SITE}/rest/api/3/search/jql").mock(
        return_value=Response(200, json={"issues": [], "nextPageToken": None})
    )
    out = _err(await atlassian_jira_search_issues(jql="project = ABC", limit=500))
    assert route.called
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body["jql"] == "project = ABC"
    assert sent_body["maxResults"] == 100  # capped at hard limit
    assert out["issues"] == []


# --- TC3 / AC2 ---------------------------------------------------------


@respx.mock
async def test_jira_get_issue_returns_structured_fields(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/rest/api/3/issue/ABC-1").mock(
        return_value=Response(
            200,
            json={
                "key": "ABC-1",
                "fields": {
                    "summary": "Fix the thing",
                    "status": {"name": "In Progress"},
                    "assignee": {"emailAddress": "jane@acme.com"},
                    "description": "details",
                    "comment": {"total": 2},
                },
            },
        )
    )
    out = _err(await atlassian_jira_get_issue(issue_key="ABC-1"))
    assert out == {
        "key": "ABC-1",
        "summary": "Fix the thing",
        "status": "In Progress",
        "assignee": "jane@acme.com",
        "description": "details",
        "comment_count": 2,
    }


# --- TC5 / AC3 ---------------------------------------------------------


@respx.mock
async def test_jira_create_issue_sends_required_fields(bound_creds: AtlassianCredentials):
    route = respx.post(f"{SITE}/rest/api/3/issue").mock(return_value=Response(201, json={"key": "ABC-9"}))
    out = _err(
        await atlassian_jira_create_issue(
            project_key="ABC", summary="New bug", issue_type="Bug", description="repro steps"
        )
    )
    sent = json.loads(route.calls[0].request.content)
    assert sent["fields"]["project"] == {"key": "ABC"}
    assert sent["fields"]["summary"] == "New bug"
    assert sent["fields"]["issuetype"] == {"name": "Bug"}
    assert out == {"key": "ABC-9", "url": f"{SITE}/browse/ABC-9"}


@respx.mock
async def test_jira_create_issue_invalid_project_maps_to_invalid_argument(bound_creds: AtlassianCredentials):
    respx.post(f"{SITE}/rest/api/3/issue").mock(
        return_value=Response(400, json={"errorMessages": ["project key ZZZ does not exist"]})
    )
    out = _err(
        await atlassian_jira_create_issue(project_key="ZZZ", summary="x", issue_type="Bug", description=None)
    )
    assert out["error"]["code"] == "invalid_argument"


# --- TC7 / AC4 ---------------------------------------------------------


@respx.mock
async def test_jira_update_issue_sends_only_changed_fields(bound_creds: AtlassianCredentials):
    route = respx.put(f"{SITE}/rest/api/3/issue/ABC-1").mock(return_value=Response(204))
    out = _err(await atlassian_jira_update_issue(issue_key="ABC-1", fields={"summary": "Renamed"}))
    sent = json.loads(route.calls[0].request.content)
    assert list(sent["fields"].keys()) == ["summary"]
    assert out == {"updated": True}


async def test_jira_update_issue_unsupported_field_maps_to_invalid_argument(bound_creds: AtlassianCredentials):
    out = _err(await atlassian_jira_update_issue(issue_key="ABC-1", fields={"made_up_field": "x"}))
    assert out["error"]["code"] == "invalid_argument"
    assert "made_up_field" in out["error"]["message"]


# --- TC8 / AC5 ---------------------------------------------------------


@respx.mock
async def test_jira_transition_issue_lists_available_transitions_on_invalid_target(
    bound_creds: AtlassianCredentials,
):
    respx.get(f"{SITE}/rest/api/3/issue/ABC-1/transitions").mock(
        return_value=Response(
            200,
            json={"transitions": [{"id": "11", "name": "In Progress"}, {"id": "21", "name": "Done"}]},
        )
    )
    out = _err(await atlassian_jira_transition_issue(issue_key="ABC-1", target_status="Blocked"))
    assert out["error"]["code"] == "invalid_argument"
    assert "In Progress" in out["error"]["message"]
    assert "Done" in out["error"]["message"]


# --- TC10 / AC6 ----------------------------------------------------------


@respx.mock
async def test_jira_add_comment_posts_comment_body(bound_creds: AtlassianCredentials):
    route = respx.post(f"{SITE}/rest/api/3/issue/ABC-1/comment").mock(
        return_value=Response(201, json={"id": "10042"})
    )
    out = _err(await atlassian_jira_add_comment(issue_key="ABC-1", body="looks good"))
    sent = json.loads(route.calls[0].request.content)
    assert sent["body"]["content"][0]["content"][0]["text"] == "looks good"
    assert out == {"comment_id": "10042"}


# --- TC11 / AC7 ----------------------------------------------------------


@respx.mock
async def test_jira_list_projects_returns_key_and_name(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/rest/api/3/project/search").mock(
        return_value=Response(
            200,
            json={"values": [{"key": "ABC", "name": "Acme Core", "projectTypeKey": "software"}]},
        )
    )
    out = _err(await atlassian_jira_list_projects())
    assert out == {"projects": [{"key": "ABC", "name": "Acme Core", "project_type": "software"}]}


# --- TC12 / AC8 ----------------------------------------------------------


@respx.mock
async def test_confluence_search_pages_builds_cql_request(bound_creds: AtlassianCredentials):
    route = respx.get(f"{SITE}/wiki/rest/api/search").mock(return_value=Response(200, json={"results": []}))
    out = _err(await atlassian_confluence_search_pages(cql='space = "ENG"'))
    assert route.called
    assert route.calls[0].request.url.params["cql"] == 'space = "ENG"'
    assert out["pages"] == []


# --- TC13 / AC9 ----------------------------------------------------------


@respx.mock
async def test_confluence_get_page_returns_storage_body(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/wiki/api/v2/pages/123").mock(
        return_value=Response(
            200,
            json={
                "id": "123",
                "title": "Runbook",
                "spaceId": "7",
                "body": {"storage": {"value": "<p>Hello</p>"}},
                "version": {"number": 3},
            },
        )
    )
    out = _err(await atlassian_confluence_get_page(page_id="123"))
    assert out == {"id": "123", "title": "Runbook", "space": "7", "body": "Hello", "version": 3}


@respx.mock
async def test_confluence_get_page_not_found_maps_to_not_found(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/wiki/api/v2/pages/999").mock(return_value=Response(404, json={}))
    out = _err(await atlassian_confluence_get_page(page_id="999"))
    assert out["error"]["code"] == "not_found"


# --- TC14 / AC10 ---------------------------------------------------------


@respx.mock
async def test_confluence_create_page_maps_duplicate_title_to_invalid_argument(
    bound_creds: AtlassianCredentials,
):
    respx.get(f"{SITE}/wiki/api/v2/spaces").mock(
        return_value=Response(200, json={"results": [{"id": "7", "key": "ENG"}]})
    )
    respx.post(f"{SITE}/wiki/api/v2/pages").mock(
        return_value=Response(400, json={"errors": [{"title": "A page with this title already exists"}]})
    )
    out = _err(
        await atlassian_confluence_create_page(space_key="ENG", title="Runbook", body_html="<p>x</p>")
    )
    assert out["error"]["code"] == "invalid_argument"


# --- TC16 / AC11 -----------------------------------------------------------


@respx.mock
async def test_confluence_update_page_increments_version(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/wiki/api/v2/pages/123").mock(
        return_value=Response(200, json={"id": "123", "title": "Runbook"})
    )
    route = respx.put(f"{SITE}/wiki/api/v2/pages/123").mock(
        return_value=Response(200, json={"version": {"number": 4}})
    )
    out = _err(
        await atlassian_confluence_update_page(page_id="123", body_html="<p>v4</p>", current_version=3)
    )
    sent = json.loads(route.calls[0].request.content)
    assert sent["version"]["number"] == 4
    assert out == {"version": 4}


@respx.mock
async def test_confluence_update_page_stale_version_maps_to_conflict_error(
    bound_creds: AtlassianCredentials,
):
    respx.get(f"{SITE}/wiki/api/v2/pages/123").mock(
        return_value=Response(200, json={"id": "123", "title": "Runbook"})
    )
    respx.put(f"{SITE}/wiki/api/v2/pages/123").mock(return_value=Response(409, json={}))
    out = _err(
        await atlassian_confluence_update_page(page_id="123", body_html="<p>stale</p>", current_version=1)
    )
    assert out["error"]["code"] == "invalid_argument"
    assert "conflict" in out["error"]["message"]


# --- TC17 / AC12 -----------------------------------------------------------


@respx.mock
async def test_confluence_list_spaces_returns_key_and_name(bound_creds: AtlassianCredentials):
    respx.get(f"{SITE}/wiki/api/v2/spaces").mock(
        return_value=Response(200, json={"results": [{"key": "ENG", "name": "Engineering"}]})
    )
    out = _err(await atlassian_confluence_list_spaces())
    assert out == {"spaces": [{"key": "ENG", "name": "Engineering"}]}
