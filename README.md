# atlassian-mcp

MCP server for Atlassian Jira Cloud and Confluence Cloud. Gives an MCP-connected
agent (Claude, ChatGPT, Cursor, or any MCP-compatible client) read and core
write access to Jira issues and Confluence pages over Atlassian's public Cloud
REST APIs: search, read, create, update, transition (Jira), and comment, plus
the project/space listings needed to address them. Credentials travel only in
per-request headers and are never persisted by this service (see
[Authentication headers](#authentication-headers)).

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

Every tool call must carry all three headers below. Credentials are read
per-request only -- never persisted, never logged, never echoed back in a
response. Missing any of the three returns HTTP 401 listing exactly the
missing header names, and no outbound call is made to Atlassian.

| Header | Required | Meaning |
|---|---|---|
| `X-Atlassian-Site` | yes | Cloud site base URL, e.g. `https://acme.atlassian.net` (no trailing slash) |
| `X-Atlassian-Email` | yes | Account email used for Basic auth |
| `X-Atlassian-Api-Token` | yes | API token from `id.atlassian.com/manage-profile/security/api-tokens` |

v1 supports API-token Basic auth only; OAuth 2.0 (3LO) is not supported (see
`docs/tickets/PRD-21297.md` § Decisions made by DEV01, decision 1).

## Tools (12)

| Tool | What it does |
|---|---|
| `atlassian_jira_search_issues` | Search Jira issues by JQL |
| `atlassian_jira_get_issue` | Get one Jira issue by key |
| `atlassian_jira_create_issue` | Create a Jira issue |
| `atlassian_jira_update_issue` | Update fields on a Jira issue |
| `atlassian_jira_transition_issue` | Move a Jira issue to a different status |
| `atlassian_jira_add_comment` | Add a comment to a Jira issue |
| `atlassian_jira_list_projects` | List Jira projects |
| `atlassian_confluence_search_pages` | Search Confluence pages by CQL |
| `atlassian_confluence_get_page` | Get one Confluence page by id |
| `atlassian_confluence_create_page` | Create a Confluence page |
| `atlassian_confluence_update_page` | Update a Confluence page (optimistic-locked by version) |
| `atlassian_confluence_list_spaces` | List Confluence spaces |

Every error is a structured envelope `{"error": {"code", "message", "retryable"}}`
with `code` one of `not_configured`, `unauthorized`, `not_found`,
`invalid_argument`, `rate_limited`, `upstream_error` -- never a raw
exception or stack trace. Full request/response contract:
`docs/tickets/PRD-21297.md` § Data & API contract.

## Local development

```bash
uv sync --dev
uv run pytest
uv run python -m uvicorn atlassian_mcp.server:app --app-dir src --host 0.0.0.0 --port 8080
```

`GET /health` is a local liveness probe (no headers needed). `POST /mcp` is
the Streamable HTTP MCP endpoint and requires the three headers above.

## License

Apache-2.0. Copyright MSPbots.ai.
