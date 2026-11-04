"""Per-request credential handling.

Three iron laws (SOP "Operating model"), all enforced here:
  1. Credentials only ever come from request headers -- never env, never disk.
  2. Requests are fully isolated -- a contextvars.ContextVar holds the
     credential set for exactly the lifetime of one request, reset() in a
     finally block. No module-level or global variable ever stores a
     credential (AC14).
  3. The service holds no state of its own between requests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SITE_HEADER = "X-Atlassian-Site"
EMAIL_HEADER = "X-Atlassian-Email"
API_TOKEN_HEADER = "X-Atlassian-Api-Token"

REQUIRED_HEADERS = (SITE_HEADER, EMAIL_HEADER, API_TOKEN_HEADER)


@dataclass(frozen=True, slots=True)
class AtlassianCredentials:
    site: str
    email: str
    api_token: str


_credentials: ContextVar[AtlassianCredentials | None] = ContextVar("atlassian_credentials", default=None)


def current_credentials() -> AtlassianCredentials:
    """Read the credential set stashed for the in-flight request.

    Raises RuntimeError if called outside a request that passed through
    CredentialMiddleware -- that is a programming error (a tool invoked
    without going through /mcp), not a user-facing condition.
    """
    creds = _credentials.get()
    if creds is None:
        raise RuntimeError("no Atlassian credentials bound to the current request context")
    return creds


class CredentialMiddleware(BaseHTTPMiddleware):
    """Validates the three credential headers and binds them to a ContextVar.

    Only applies to the /mcp path -- /health must stay reachable with no
    headers at all, since it is a local liveness probe (SOP §1.1).
    """

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        missing = [h for h in REQUIRED_HEADERS if not request.headers.get(h)]
        if missing:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": "missing required headers: " + ", ".join(missing),
                        "retryable": False,
                    }
                },
            )

        creds = AtlassianCredentials(
            site=request.headers[SITE_HEADER].rstrip("/"),
            email=request.headers[EMAIL_HEADER],
            api_token=request.headers[API_TOKEN_HEADER],
        )
        token = _credentials.set(creds)
        try:
            return await call_next(request)
        finally:
            _credentials.reset(token)


@asynccontextmanager
async def bind_credentials(creds: AtlassianCredentials):
    """Test-only helper: bind credentials for the duration of a `with` block.

    Production code never calls this directly -- CredentialMiddleware does
    the binding for real requests. Tests use it to exercise tool functions
    without going through the ASGI stack.
    """
    token = _credentials.set(creds)
    try:
        yield
    finally:
        _credentials.reset(token)
