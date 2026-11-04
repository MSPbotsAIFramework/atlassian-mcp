"""ASGI app: FastMCP Streamable-HTTP server + /health, stateless, no DNS-rebinding trap.

`mcp` is created first so the tool modules (imported below for their
registration side effects) can do `from atlassian_mcp.server import mcp`
without a real import cycle -- by the time Python starts executing
`atlassian_mcp.tools.jira_tools`, this module's `mcp` attribute already
exists in `sys.modules`.
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from atlassian_mcp.middleware import CredentialMiddleware
from atlassian_mcp.settings import settings

mcp: FastMCP = FastMCP(
    name="atlassian-mcp",
    instructions=(
        "Jira Cloud and Confluence Cloud for one Atlassian site, per request. "
        "Jira: search issues by JQL, read/create/update/transition issues, add "
        "comments, list projects. Confluence: search pages by CQL, read/create/"
        "update pages, list spaces. Every call needs the three Atlassian "
        "credential headers (site, email, API token); without them every tool "
        "returns a 401 before any request leaves this service. Searches and "
        "lists are paginated (default 25, max 100) -- call again with the "
        "returned cursor for more instead of assuming one call returns "
        "everything. Write tools take explicit ids (issue key, page id + "
        "version) only; there is no fuzzy title-based write."
    ),
)

# Imported for their @mcp.tool() registration side effects only.
from atlassian_mcp.tools import confluence_tools, jira_tools  # noqa: E402,F401


async def _health(_request: Request) -> JSONResponse:
    """Local liveness probe -- never calls Atlassian, never needs headers."""
    return JSONResponse({"status": "ok"})


def build_app():
    """Build the Streamable-HTTP app: POST /mcp (stateless) + GET /health."""
    app = mcp.http_app(
        path="/mcp",
        stateless_http=True,
        middleware=[Middleware(CredentialMiddleware)],
    )
    app.router.routes.insert(0, Route("/health", _health, methods=["GET"]))
    return app


app = build_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
