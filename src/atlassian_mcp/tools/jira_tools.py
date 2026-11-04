"""The 7 atlassian_jira_* tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from atlassian_mcp.clients import jira_client
from atlassian_mcp.errors import as_tool_result
from atlassian_mcp.middleware import current_credentials
from atlassian_mcp.server import mcp


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_jira_search_issues(
    jql: str,
    limit: int = 25,
    fields: list[str] | None = None,
) -> str:
    """Search Jira issues by JQL.

    Returns matching issues (key, summary, status, assignee, updated) up to
    `limit` (default 25, hard cap 100). No matches returns an empty list,
    never an error. `fields` restricts which issue fields are returned.
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.search_issues(creds, jql, limit=limit, fields=fields))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_jira_get_issue(issue_key: str) -> str:
    """Get one Jira issue by key.

    Returns key, summary, status, assignee, description, and comment count.
    An issue key that does not exist returns a structured not_found error.
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.get_issue(creds, issue_key))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
async def atlassian_jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str,
    description: str | None = None,
) -> str:
    """Create a Jira issue in an existing project.

    Returns the new issue's key and web URL. A project key that does not
    exist returns a structured invalid_argument error.
    """
    creds = current_credentials()
    return await as_tool_result(
        jira_client.create_issue(
            creds,
            project_key=project_key,
            summary=summary,
            issue_type=issue_type,
            description=description,
        )
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
async def atlassian_jira_update_issue(issue_key: str, fields: dict) -> str:
    """Update one or more fields on an existing Jira issue.

    Only the fields present in `fields` are changed (summary, description,
    assignee). Any other field name returns a structured invalid_argument
    error naming the rejected field.
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.update_issue(creds, issue_key, fields))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
async def atlassian_jira_transition_issue(issue_key: str, target_status: str) -> str:
    """Move a Jira issue to a different status.

    Only succeeds if `target_status` is a transition actually available
    from the issue's current status; otherwise returns a structured error
    listing the transitions that are actually available.
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.transition_issue(creds, issue_key, target_status))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
async def atlassian_jira_add_comment(issue_key: str, body: str) -> str:
    """Add a comment to a Jira issue.

    Returns the new comment's id.
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.add_comment(creds, issue_key, body))


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_jira_list_projects(limit: int = 25) -> str:
    """List Jira projects visible to the supplied credentials.

    Returns key, name, and project type for each project, up to `limit`
    (default 25, hard cap 100).
    """
    creds = current_credentials()
    return await as_tool_result(jira_client.list_projects(creds, limit=limit))
