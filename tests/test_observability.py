"""Regression tests for PRD-21297 code-review round 1, finding 2.

The tech design's Goals / Non-functional "Observability" sections promise a
structured, per-tool-call audit log: a request id correlating which tool ran
to which Atlassian endpoint it hit, without ever logging credential values
or full request/response bodies (JQL/CQL text included). Round 1 found zero
implementing code. These tests pin the fix in
`atlassian_mcp.errors.as_tool_result` and `clients.base.request_with_retry`.
"""

from __future__ import annotations

import logging
import re

import respx
from httpx import Response

from atlassian_mcp.errors import as_tool_result
from atlassian_mcp.middleware import AtlassianCredentials
from atlassian_mcp.tools.jira_tools import atlassian_jira_create_issue, atlassian_jira_list_projects, atlassian_jira_search_issues

SITE = "https://acme.atlassian.net"


def _request_ids(text: str) -> set[str]:
    return set(re.findall(r"request_id=(\S+)", text))


@respx.mock
async def test_successful_tool_call_logs_correlated_request_id_tool_and_endpoint(
    caplog, bound_creds: AtlassianCredentials
):
    caplog.set_level(logging.INFO, logger="atlassian_mcp")
    respx.get(f"{SITE}/rest/api/3/project/search").mock(
        return_value=Response(200, json={"values": [{"key": "ABC", "name": "Acme", "projectTypeKey": "software"}]})
    )

    await atlassian_jira_list_projects()

    tool_lines = [r.message for r in caplog.records if r.message.startswith("tool call done")]
    endpoint_lines = [r.message for r in caplog.records if r.message.startswith("atlassian call")]
    assert len(tool_lines) == 1, caplog.text
    assert len(endpoint_lines) == 1, caplog.text
    assert "tool=atlassian_jira_list_projects" in tool_lines[0]
    assert "outcome=success" in tool_lines[0]
    assert re.search(r"latency_ms=\d+\.\d", tool_lines[0])
    assert "endpoint=/rest/api/3/project/search" in endpoint_lines[0]
    assert "status=200" in endpoint_lines[0]

    # Same correlation id ties the tool-level line to the endpoint-level line.
    tool_ids = _request_ids(tool_lines[0])
    endpoint_ids = _request_ids(endpoint_lines[0])
    assert tool_ids and tool_ids == endpoint_ids


@respx.mock
async def test_expected_error_path_logs_the_error_code_as_outcome(caplog, bound_creds: AtlassianCredentials):
    caplog.set_level(logging.INFO, logger="atlassian_mcp")
    respx.post(f"{SITE}/rest/api/3/issue").mock(
        return_value=Response(400, json={"errorMessages": ["project key ZZZ does not exist"]})
    )

    await atlassian_jira_create_issue(project_key="ZZZ", summary="x", issue_type="Bug", description=None)

    tool_lines = [r.message for r in caplog.records if r.message.startswith("tool call done")]
    assert len(tool_lines) == 1, caplog.text
    assert "tool=atlassian_jira_create_issue" in tool_lines[0]
    assert "outcome=invalid_argument" in tool_lines[0]


@respx.mock
async def test_logs_never_contain_credential_values_or_jql_text(caplog, bound_creds: AtlassianCredentials):
    caplog.set_level(logging.INFO, logger="atlassian_mcp")
    respx.post(f"{SITE}/rest/api/3/search/jql").mock(return_value=Response(200, json={"issues": []}))

    jql = "project = SECRET-PROJECT"
    await atlassian_jira_search_issues(jql=jql)

    assert bound_creds.api_token not in caplog.text
    assert bound_creds.email not in caplog.text
    assert jql not in caplog.text
    # The endpoint line must be the bare path, no query string, no body.
    endpoint_lines = [r.message for r in caplog.records if r.message.startswith("atlassian call")]
    assert endpoint_lines and "endpoint=/rest/api/3/search/jql" in endpoint_lines[0]


async def test_unexpected_exception_still_logs_request_id_and_tool_name(caplog):
    caplog.set_level(logging.INFO, logger="atlassian_mcp")

    async def _boom():
        raise RuntimeError("boom")

    await as_tool_result(_boom(), tool_name="atlassian_jira_get_issue")

    exc_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(exc_records) == 1, caplog.text
    assert "tool=atlassian_jira_get_issue" in exc_records[0].message
    assert _request_ids(exc_records[0].message)
