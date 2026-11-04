# PRD-21297 · Code review

## Round 1 · 2026-11-04 · reviewed dev/PRD-21297 @ 1c96663 (base main @ 4348cb8)

Verdict: changes requested

### Findings

1. [must-fix] docs/tickets/PRD-21297.md:283 — The repo contains a Chinese-language quote: `Checklist "用 Agent 真实跑通一遍典型业务流程"`. SOP §0.4 / the Checklist's "日志与敏感信息" section require the entire repo (code, comments, tool descriptions, errors, logs, **documentation**, commit messages) to be English-only, and `mcp-track.md` §4.3 lists "仓库里没有中文" as an unconditional must-fix line for MCP repos. Independently re-running the exact scan command the Self-test section claims to have run — `grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .` on the committed tree at `1c96663` — does produce output (this very line), contradicting the Self-test's own "Chinese-character scan: ... → no output" claim a few lines above it in the same document. Fix: rephrase the Checklist-item reference in English instead of quoting the Chinese Checklist text verbatim, re-run the scan, and correct the Self-test note to match the real (now-clean) result.

2. [must-fix] src/atlassian_mcp/errors.py:93 (and the rest of `src/atlassian_mcp/`) — The tech design's Product design § Goals ("Every call is auditable: structured logs correlate a request id to which tool ran and which Atlassian endpoint it hit, without logging the credential values or full issue/page bodies") and § Non-functional "Observability" ("structured log per tool call — request id, tool name, Atlassian endpoint + HTTP status, latency") commit to a structured, per-call audit log. The implementation has exactly one logging statement in the whole service, `logger.exception("unexpected error while running an Atlassian MCP tool")` in `as_tool_result`'s last-resort `except Exception` branch (errors.py:93) — it fires only on an unanticipated crash, carries no request id / tool name / endpoint / status / latency, and nothing else in `middleware.py`, `clients/base.py`, `clients/jira_client.py`, `clients/confluence_client.py`, or either `tools/*.py` module logs anything (`grep -rn "request_id\|req_id\|correlation\|logging\." src/atlassian_mcp` has no further hits). So neither the success path nor the expected-`AtlassianMcpError` path is audited at all, and there is no request id anywhere in the codebase — this is a stated v1 Goal with zero implementing code, not an edge case. SOP §14 Checklist's "日志与敏感信息" section also lists "结构化日志带 request-id" as a required pre-delivery item. Fix: add a per-request correlation id (e.g. generated in `CredentialMiddleware` and threaded through, or wrapped around `as_tool_result`) and emit one structured log line per tool call on both the success and the expected-error path (tool name, Atlassian endpoint, HTTP status, latency), still never logging header values, JQL/CQL text, or issue/page bodies, matching the already-written Non-functional section.

### Suggestions

1. [suggestion] SOP §14 Checklist "带 Header 真跑一次 `tools/call` 验证" — the Self-test's manual smoke test exercises `initialize` and `tools/list` over the real HTTP transport (with placeholder headers) but not an actual `tools/call` JSON-RPC round trip. The per-tool business logic is already thoroughly covered by the mocked `respx` unit tests (which call the tool functions directly), so the residual risk is limited to FastMCP's own `tools/call` dispatch/argument-parsing layer — low, and already implicitly exercised by `tools/list` succeeding over the same transport. Worth adding one real-transport `tools/call` smoke (e.g. `atlassian_jira_list_projects` with placeholder headers, asserting on the structured-error shape since there is no live account) so this Checklist line is satisfied directly rather than by inference.

### Notes verified during review (no finding, recorded for the next reader)

- `uv run pytest -q` on `1c96663`: 20 passed (matches the Self-test claim).
- `uv lock --check`: resolves cleanly, lockfile is in sync.
- README "MSPbots Connector" section: diffed programmatically against `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` — byte-for-byte match.
- Installed `fastmcp` version: `4.1.6`, matches the Self-test's DNS-rebinding-guard note.
- `docker build --platform linux/amd64`: also not runnable in the review leg's environment (`permission denied` on `/var/run/docker.sock`), same as the dev leg's sandbox — not a new gap, carried forward as a known limitation for whoever has Docker access.
- `gitleaks`: also not installed in this environment — same known gap as the dev leg, not re-raised as a new finding.
