---
name: mcp-auth-lifecycle-manager
version: "1.0"
category: openclaw-native
description: Tracks MCP auth dependencies, token expiry, missing env vars, and refresh readiness so MCP servers do not silently fail after credentials age out.
stateful: true
cron: "0 */6 * * *"
---

# MCP Auth Lifecycle Manager

## What it does

MCP outages often start as auth problems, not transport problems. A server can be reachable but still unusable because a token expired, a refresh command is missing, or a required environment variable is no longer set.

MCP Auth Lifecycle Manager keeps a per-server auth ledger: expiry windows, refresh cadence, missing env vars, interactive login requirements, and the last successful refresh event.

## When to invoke

- After adding or changing an MCP server
- Before unattended runs that depend on OAuth or rotating tokens
- When an MCP server is healthy but tool calls still fail with auth errors
- As a scheduled audit every 6 hours

## What it checks

| Check | What it means |
|---|---|
| `TOKEN_MISSING` | Required auth environment variable is not set |
| `TOKEN_EXPIRING` | Auth expires within the next 24 hours |
| `TOKEN_EXPIRED` | Auth is already past its expiry timestamp |
| `REFRESH_UNDEFINED` | Server has auth but no refresh command or refresh guidance |
| `REFRESH_OVERDUE` | Last successful refresh is older than the expected interval |
| `STATIC_SECRET_IN_CONFIG` | Token or secret appears to be hardcoded in MCP config |
| `INTERACTIVE_REFRESH` | Refresh still requires a browser or manual login |

## How to use

```bash
python3 manage.py --scan
python3 manage.py --scan --server github
python3 manage.py --status
python3 manage.py --plan github
python3 manage.py --record-refresh github --result success --note "gh auth refresh completed"
python3 manage.py --record-refresh github --result success --expires-at 2026-04-20T12:00:00
python3 manage.py --history
python3 manage.py --format json
```

## Optional auth registry

Use `~/.openclaw/config/mcp-auth.yaml` or `mcp-auth.json` to record provider-specific lifecycle data:

```yaml
servers:
  github:
    provider: github
    auth_type: oauth
    expires_at: "2026-04-20T12:00:00"
    refresh_command: "gh auth refresh -h github.com"
    refresh_interval_hours: 12
    interactive_refresh: false
    notes: "Bot token rotated by SSO policy"
```

## Difference from mcp-health-checker

`mcp-health-checker` asks: "Can I reach the server right now?"

`mcp-auth-lifecycle-manager` asks: "Will auth still work tomorrow, and do I know how to recover it when it stops?"

## State

State file: `~/.openclaw/skill-state/mcp-auth-lifecycle-manager/state.yaml`

Fields: `last_scan_at`, `last_config_path`, `last_registry_path`, `servers`, `refresh_history`.
