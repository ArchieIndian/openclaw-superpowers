---
name: mcp-health-checker
version: "1.0"
category: openclaw-native
description: Monitors MCP server connections for health, latency, and availability — detects stale connections, timeouts, and unreachable servers before they cause silent tool failures.
stateful: true
cron: "0 */6 * * *"
---

# MCP Health Checker

## What it does

MCP (Model Context Protocol) servers are how OpenClaw connects to external tools — but connections go stale silently. A crashed MCP server doesn't throw an error until the agent tries to use it, causing confusing mid-task failures.

MCP Health Checker proactively monitors all configured MCP connections. It pings servers, measures latency, tracks uptime history, and alerts you before a stale connection causes a problem.

Inspired by OpenLobster's MCP connection health monitoring and OAuth 2.1+PKCE token refresh tracking.

## When to invoke

- Automatically every 6 hours (cron) — silent background health check
- Manually before starting a task that depends on MCP tools
- When an MCP tool call fails unexpectedly — diagnose the connection
- After restarting MCP servers — verify all connections restored

## Health checks performed

| Check | What it tests | Severity on failure |
|---|---|---|
| REACHABLE | Server responds to connection probe | CRITICAL |
| LATENCY | Response time under threshold (default: 5s) | HIGH |
| STALE | Connection age exceeds max (default: 24h) | HIGH |
| TOOL_COUNT | Server exposes expected number of tools | MEDIUM |
| CONFIG_VALID | MCP config entry has required fields | MEDIUM |
| AUTH_EXPIRY | OAuth/API token approaching expiration | HIGH |

## How to use

```bash
python3 check.py --ping                     # Ping all configured MCP servers
python3 check.py --ping --server <name>     # Ping a specific server
python3 check.py --ping --timeout 3         # Custom timeout in seconds
python3 check.py --status                   # Last check summary from state
python3 check.py --history                  # Show past check results
python3 check.py --config                   # Validate MCP config entries
python3 check.py --format json              # Machine-readable output
```

## Cron wakeup behaviour

Every 6 hours:

1. Read MCP server configuration from `~/.openclaw/config/` (YAML/JSON)
2. For each configured server:
   - Attempt connection probe (TCP or HTTP depending on transport)
   - Measure response latency
   - Check connection age against staleness threshold
   - Verify tool listing matches expected count (if tracked)
   - Check auth token expiry (if applicable)
3. Update state with per-server health records
4. Print summary: healthy / degraded / unreachable counts
5. Exit 1 if any CRITICAL findings

## Procedure

**Step 1 — Run a health check**

```bash
python3 check.py --ping
```

Review the output. Healthy servers show a green check. Degraded servers show latency warnings. Unreachable servers show a critical alert.

**Step 2 — Diagnose a specific server**

```bash
python3 check.py --ping --server filesystem
```

Detailed output for a single server: latency, last seen, tool count, auth status.

**Step 3 — Validate configuration**

```bash
python3 check.py --config
```

Checks that all MCP config entries have the required fields (`command`, `args` or `url` depending on transport type).

**Step 4 — Review history**

```bash
python3 check.py --history
```

Shows uptime trends over the last 20 checks. Spot servers that are intermittently failing.

## State

Per-server health records and check history stored in `~/.openclaw/skill-state/mcp-health-checker/state.yaml`.

Fields: `last_check_at`, `servers` list, `check_history`.

## Notes

- Does not modify MCP configuration — read-only monitoring
- Connection probes use the same transport as the MCP server (stdio subprocess spawn or HTTP GET)
- For stdio servers: probes verify the process can start and respond to `initialize`
- For HTTP/SSE servers: probes send a health-check HTTP request
- Latency threshold configurable via `--timeout` (default: 5s)
- Staleness threshold configurable via `--max-age` (default: 24h)
