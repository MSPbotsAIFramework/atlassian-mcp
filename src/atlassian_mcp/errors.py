"""Structured error envelope shared by every tool.

Every tool-level failure returns this envelope as its JSON string result --
never a raised exception, never a raw Atlassian response, never a stack
trace (PRD-21297 tech design § Data & API contract).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Literal

logger = logging.getLogger("atlassian_mcp")

ErrorCode = Literal[
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
]


class AtlassianMcpError(Exception):
    """Carries a structured error envelope through tool code.

    Tool functions catch this (or raise it directly) and turn it into the
    JSON envelope string that is the tool's return value -- the MCP
    transport never sees a raised exception for an expected failure mode.
    """

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.retryable = retryable

    def to_envelope(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }

    def to_json(self) -> str:
        return json.dumps(self.to_envelope(), ensure_ascii=False, separators=(",", ":"))


def error_json(code: ErrorCode, message: str, *, retryable: bool = False) -> str:
    """Convenience for building an error envelope string without raising."""
    return AtlassianMcpError(code, message, retryable=retryable).to_json()


def map_http_status(status_code: int, *, upstream_message: str | None = None) -> AtlassianMcpError:
    """Map an Atlassian REST HTTP status to a structured error code.

    Callers that have a more specific mapping (e.g. a 400 that is
    specifically a duplicate-title conflict) should not call this and
    instead build the AtlassianMcpError directly -- this is the generic
    fallback by status code family.
    """
    message = upstream_message or f"Atlassian returned HTTP {status_code}"
    if status_code in (401, 403):
        return AtlassianMcpError("unauthorized", message, retryable=False)
    if status_code == 404:
        return AtlassianMcpError("not_found", message, retryable=False)
    if status_code == 400 or status_code == 422:
        return AtlassianMcpError("invalid_argument", message, retryable=False)
    if status_code == 429:
        return AtlassianMcpError("rate_limited", message, retryable=True)
    if status_code >= 500:
        return AtlassianMcpError("upstream_error", message, retryable=True)
    return AtlassianMcpError("upstream_error", message, retryable=False)


async def as_tool_result(awaitable: Awaitable[Any]) -> str:
    """Run a tool body and turn it into the tool's string return value.

    Every MCP tool in this service returns a compact JSON string -- either
    the success payload or this error envelope -- and never raises. An
    uncaught exception here would otherwise surface to the gateway as a
    raw ToolError with a stack trace, which SOP §4 explicitly forbids.
    """
    try:
        result = await awaitable
    except AtlassianMcpError as exc:
        return exc.to_json()
    except Exception as exc:  # noqa: BLE001 -- last-resort guard, see docstring
        logger.exception("unexpected error while running an Atlassian MCP tool")
        return error_json("upstream_error", f"unexpected error: {exc}", retryable=False)
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
