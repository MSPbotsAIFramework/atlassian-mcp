"""Structured error envelope shared by every tool.

Every tool-level failure returns this envelope as its JSON string result --
never a raised exception, never a raw Atlassian response, never a stack
trace (PRD-21297 tech design § Data & API contract).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Awaitable, Literal

logger = logging.getLogger("atlassian_mcp")


def _configure_default_logging() -> None:
    """Make sure the audit log below actually reaches stdout in production.

    Nothing else in this service calls `logging.basicConfig()`, and the
    Docker image's `CMD` runs `uvicorn atlassian_mcp.server:app` directly --
    `server.main()` is never executed in production, so there is no other
    place that would configure this. Without this, the root logger's default
    level (WARNING) would silently drop every `logger.info(...)` call below
    even once deployed, making the whole audit-log fix a no-op outside of
    tests (`caplog`-based tests attach their own handler/level regardless of
    this, which is how round 1 passed tests while production would still
    have logged nothing). Idempotent and only touches this one named logger,
    not the root logger, so it never changes any other module's logging.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    if logger.level == logging.NOTSET or logger.level > logging.INFO:
        logger.setLevel(logging.INFO)


_configure_default_logging()

# Correlation id for the tool call currently in flight (PRD-21297 tech design
# § Non-functional "Observability": one id ties the tool-call log line in
# this module to the per-endpoint log lines emitted by
# clients/base.py::request_with_retry for the same call). Generated fresh by
# as_tool_result for every invocation -- never a global/shared value, in
# keeping with the per-request isolation this service otherwise guarantees.
_call_id: ContextVar[str | None] = ContextVar("atlassian_mcp_call_id", default=None)


def current_call_id() -> str | None:
    """The in-flight tool call's correlation id, or None outside one.

    Returns None when called from code that never went through
    `as_tool_result` (e.g. a client function exercised directly in a test) --
    callers must tolerate a missing id rather than fail.
    """
    return _call_id.get()

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


async def as_tool_result(awaitable: Awaitable[Any], *, tool_name: str) -> str:
    """Run a tool body and turn it into the tool's string return value.

    Every MCP tool in this service returns a compact JSON string -- either
    the success payload or this error envelope -- and never raises. An
    uncaught exception here would otherwise surface to the gateway as a
    raw ToolError with a stack trace, which SOP §4 explicitly forbids.

    Also emits exactly one structured audit-log line per tool call (PRD-21297
    tech design § Goals / § Non-functional "Observability"), on every path --
    success, an expected `AtlassianMcpError`, and an unexpected exception --
    carrying a fresh request id, `tool_name`, the outcome, and latency. Never
    logs credential values or request/response bodies; `request_with_retry`
    in `clients/base.py` logs the Atlassian endpoint + HTTP status per
    outbound call under the same request id so the two correlate.
    """
    call_id = uuid.uuid4().hex[:12]
    token = _call_id.set(call_id)
    started = time.monotonic()
    try:
        try:
            result = await awaitable
        except AtlassianMcpError as exc:
            logger.info(
                "tool call done request_id=%s tool=%s outcome=%s latency_ms=%.1f",
                call_id,
                tool_name,
                exc.code,
                (time.monotonic() - started) * 1000,
            )
            return exc.to_json()
        except Exception as exc:  # noqa: BLE001 -- last-resort guard, see docstring
            logger.exception(
                "unexpected error while running an Atlassian MCP tool request_id=%s tool=%s latency_ms=%.1f",
                call_id,
                tool_name,
                (time.monotonic() - started) * 1000,
            )
            return error_json("upstream_error", f"unexpected error: {exc}", retryable=False)
        logger.info(
            "tool call done request_id=%s tool=%s outcome=success latency_ms=%.1f",
            call_id,
            tool_name,
            (time.monotonic() - started) * 1000,
        )
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    finally:
        _call_id.reset(token)
