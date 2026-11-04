"""The 5 atlassian_confluence_* tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from atlassian_mcp.clients import confluence_client
from atlassian_mcp.errors import as_tool_result
from atlassian_mcp.middleware import current_credentials
from atlassian_mcp.server import mcp


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_confluence_search_pages(cql: str, limit: int = 25) -> str:
    """Search Confluence pages by CQL.

    Returns matching pages (id, title, space key, web URL) up to `limit`
    (default 25, hard cap 100). No matches returns an empty list, never an
    error.
    """
    creds = current_credentials()
    return await as_tool_result(
        confluence_client.search_pages(creds, cql, limit=limit), tool_name="atlassian_confluence_search_pages"
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_confluence_get_page(page_id: str) -> str:
    """Get one Confluence page by id.

    Returns title, space, a plain-text body extract, and the version
    number. A page id that does not exist returns a structured not_found
    error.
    """
    creds = current_credentials()
    return await as_tool_result(
        confluence_client.get_page(creds, page_id), tool_name="atlassian_confluence_get_page"
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
async def atlassian_confluence_create_page(
    space_key: str,
    title: str,
    body_html: str,
    parent_id: str | None = None,
) -> str:
    """Create a Confluence page in an existing space.

    Returns the new page's id and web URL. A title that already exists in
    that space/parent returns a structured invalid_argument error instead
    of Confluence's raw 400.
    """
    creds = current_credentials()
    return await as_tool_result(
        confluence_client.create_page(
            creds,
            space_key=space_key,
            title=title,
            body_html=body_html,
            parent_id=parent_id,
        ),
        tool_name="atlassian_confluence_create_page",
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
async def atlassian_confluence_update_page(page_id: str, body_html: str, current_version: int) -> str:
    """Update a Confluence page's content.

    Requires the page's current version number (optimistic locking): on
    success the version increments by one; a stale version number returns
    a structured conflict error instead of silently overwriting someone
    else's edit.
    """
    creds = current_credentials()
    return await as_tool_result(
        confluence_client.update_page(
            creds,
            page_id=page_id,
            body_html=body_html,
            current_version=current_version,
        ),
        tool_name="atlassian_confluence_update_page",
    )


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
)
async def atlassian_confluence_list_spaces(limit: int = 25) -> str:
    """List Confluence spaces visible to the supplied credentials.

    Returns key and name for each space, up to `limit` (default 25, hard
    cap 100).
    """
    creds = current_credentials()
    return await as_tool_result(
        confluence_client.list_spaces(creds, limit=limit), tool_name="atlassian_confluence_list_spaces"
    )
