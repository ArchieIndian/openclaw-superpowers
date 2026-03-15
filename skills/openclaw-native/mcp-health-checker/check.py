#!/usr/bin/env python3
"""
MCP Health Checker for openclaw-superpowers.

Monitors MCP server connections for health, latency, and availability.

Usage:
    python3 check.py --ping
    python3 check.py --ping --server <name>
    python3 check.py --ping --timeout 3
    python3 check.py --config
    python3 check.py --status
    python3 check.py --history
    python3 check.py --format json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "mcp-health-checker" / "state.yaml"
MAX_HISTORY = 20

# MCP config locations to search
MCP_CONFIG_PATHS = [
    OPENCLAW_DIR / "config" / "mcp.yaml",
    OPENCLAW_DIR / "config" / "mcp.json",
    OPENCLAW_DIR / "mcp.yaml",
    OPENCLAW_DIR / "mcp.json",
    Path.home() / ".config" / "openclaw" / "mcp.yaml",
    Path.home() / ".config" / "openclaw" / "mcp.json",
]

DEFAULT_TIMEOUT = 5  # seconds
DEFAULT_MAX_AGE = 24  # hours


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"servers": [], "check_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── MCP config discovery ────────────────────────────────────────────────────

def find_mcp_config() -> tuple[Path | None, dict]:
    """Find and parse MCP configuration."""
    for config_path in MCP_CONFIG_PATHS:
        if not config_path.exists():
            continue
        try:
            text = config_path.read_text()
            if config_path.suffix == ".json":
                data = json.loads(text)
            elif HAS_YAML:
                data = yaml.safe_load(text) or {}
            else:
                continue
            return config_path, data
        except Exception:
            continue
    return None, {}


def extract_servers(config: dict) -> list[dict]:
    """Extract server definitions from MCP config."""
    servers = []
    # Support both flat and nested formats
    mcp_servers = config.get("mcpServers") or config.get("servers") or config
    if isinstance(mcp_servers, dict):
        for name, defn in mcp_servers.items():
            if not isinstance(defn, dict):
                continue
            transport = "stdio"
            if "url" in defn:
                transport = "http"
            elif "command" in defn:
                transport = "stdio"
            servers.append({
                "name": name,
                "transport": transport,
                "command": defn.get("command"),
                "args": defn.get("args", []),
                "url": defn.get("url"),
                "env": defn.get("env", {}),
            })
    return servers


# ── Health checks ────────────────────────────────────────────────────────────

def probe_stdio_server(server: dict, timeout: int) -> dict:
    """Probe a stdio MCP server by attempting to start and initialize it."""
    command = server.get("command")
    args = server.get("args", [])
    if not command:
        return {
            "status": "unreachable",
            "latency_ms": 0,
            "findings": [{"check": "CONFIG_VALID", "severity": "MEDIUM",
                          "detail": "No command specified for stdio server"}],
        }

    # Build the initialize JSON-RPC request
    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-health-checker", "version": "1.0"},
        }
    }) + "\n"

    start = time.monotonic()
    try:
        env = os.environ.copy()
        env.update(server.get("env", {}))
        proc = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        stdout, stderr = proc.communicate(
            input=init_request.encode(),
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode is not None and proc.returncode != 0 and not stdout:
            return {
                "status": "unreachable",
                "latency_ms": elapsed_ms,
                "findings": [{"check": "REACHABLE", "severity": "CRITICAL",
                              "detail": f"Process exited with code {proc.returncode}"}],
            }

        # Try to parse response
        findings = []
        tool_count = 0
        try:
            response = json.loads(stdout.decode().strip().split("\n")[0])
            if "result" in response:
                caps = response["result"].get("capabilities", {})
                if "tools" in caps:
                    tool_count = -1  # Has tools capability but count unknown until list
        except (json.JSONDecodeError, IndexError):
            findings.append({"check": "REACHABLE", "severity": "HIGH",
                             "detail": "Server responded but output not valid JSON-RPC"})

        # Check latency
        status = "healthy"
        if elapsed_ms > timeout * 1000:
            findings.append({"check": "LATENCY", "severity": "HIGH",
                             "detail": f"Response time {elapsed_ms}ms exceeds {timeout}s threshold"})
            status = "degraded"
        elif elapsed_ms > (timeout * 1000) // 2:
            findings.append({"check": "LATENCY", "severity": "MEDIUM",
                             "detail": f"Response time {elapsed_ms}ms approaching threshold"})

        if findings and status == "healthy":
            status = "degraded"

        return {
            "status": status,
            "latency_ms": elapsed_ms,
            "tool_count": tool_count,
            "findings": findings,
        }

    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass
        return {
            "status": "unreachable",
            "latency_ms": elapsed_ms,
            "findings": [{"check": "LATENCY", "severity": "CRITICAL",
                          "detail": f"Server did not respond within {timeout}s"}],
        }
    except FileNotFoundError:
        return {
            "status": "unreachable",
            "latency_ms": 0,
            "findings": [{"check": "REACHABLE", "severity": "CRITICAL",
                          "detail": f"Command not found: {command}"}],
        }
    except Exception as e:
        return {
            "status": "unreachable",
            "latency_ms": 0,
            "findings": [{"check": "REACHABLE", "severity": "CRITICAL",
                          "detail": f"Probe failed: {str(e)[:100]}"}],
        }


def probe_http_server(server: dict, timeout: int) -> dict:
    """Probe an HTTP/SSE MCP server via HTTP GET."""
    url = server.get("url")
    if not url:
        return {
            "status": "unreachable",
            "latency_ms": 0,
            "findings": [{"check": "CONFIG_VALID", "severity": "MEDIUM",
                          "detail": "No URL specified for HTTP server"}],
        }

    start = time.monotonic()
    try:
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "mcp-health-checker/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            status_code = resp.status

            findings = []
            if status_code >= 400:
                findings.append({"check": "REACHABLE", "severity": "CRITICAL",
                                 "detail": f"HTTP {status_code} response"})
                return {"status": "unreachable", "latency_ms": elapsed_ms, "findings": findings}

            if elapsed_ms > timeout * 1000:
                findings.append({"check": "LATENCY", "severity": "HIGH",
                                 "detail": f"Response time {elapsed_ms}ms exceeds threshold"})

            status = "degraded" if findings else "healthy"
            return {"status": status, "latency_ms": elapsed_ms, "findings": findings}

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "unreachable",
            "latency_ms": elapsed_ms,
            "findings": [{"check": "REACHABLE", "severity": "CRITICAL",
                          "detail": f"Connection failed: {str(e)[:100]}"}],
        }


def check_staleness(server_name: str, state: dict, max_age_hours: int) -> list[dict]:
    """Check if a server connection is stale based on last seen time."""
    findings = []
    prev_servers = state.get("servers") or []
    for prev in prev_servers:
        if prev.get("name") == server_name and prev.get("last_seen_at"):
            try:
                last_seen = datetime.fromisoformat(prev["last_seen_at"])
                age = datetime.now() - last_seen
                if age > timedelta(hours=max_age_hours):
                    findings.append({
                        "check": "STALE",
                        "severity": "HIGH",
                        "detail": f"Last successful probe was {age.total_seconds()/3600:.1f}h ago "
                                  f"(threshold: {max_age_hours}h)",
                    })
            except (ValueError, TypeError):
                pass
    return findings


def validate_config_entry(server: dict) -> list[dict]:
    """Validate a server config entry has required fields."""
    findings = []
    if server["transport"] == "stdio":
        if not server.get("command"):
            findings.append({"check": "CONFIG_VALID", "severity": "MEDIUM",
                             "detail": "Missing 'command' field for stdio server"})
    elif server["transport"] == "http":
        if not server.get("url"):
            findings.append({"check": "CONFIG_VALID", "severity": "MEDIUM",
                             "detail": "Missing 'url' field for HTTP server"})
    return findings


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_ping(state: dict, server_filter: str, timeout: int, max_age: int, fmt: str) -> None:
    config_path, config = find_mcp_config()
    now = datetime.now().isoformat()

    if not config_path:
        print("No MCP configuration found. Searched:")
        for p in MCP_CONFIG_PATHS:
            print(f"  {p}")
        print("\nCreate an MCP config to enable health checking.")
        sys.exit(1)

    servers = extract_servers(config)
    if server_filter:
        servers = [s for s in servers if s["name"] == server_filter]
        if not servers:
            print(f"Error: server '{server_filter}' not found in config.")
            sys.exit(1)

    results = []
    healthy = degraded = unreachable = 0

    for server in servers:
        # Probe based on transport
        if server["transport"] == "http":
            probe = probe_http_server(server, timeout)
        else:
            probe = probe_stdio_server(server, timeout)

        # Add staleness check
        stale_findings = check_staleness(server["name"], state, max_age)
        all_findings = probe.get("findings", []) + stale_findings

        # Determine final status
        status = probe["status"]
        if status == "healthy" and stale_findings:
            status = "degraded"

        last_seen = now if status == "healthy" else None
        # Preserve previous last_seen if current probe failed
        if not last_seen:
            for prev in (state.get("servers") or []):
                if prev.get("name") == server["name"]:
                    last_seen = prev.get("last_seen_at")
                    break

        result = {
            "name": server["name"],
            "transport": server["transport"],
            "status": status,
            "latency_ms": probe.get("latency_ms", 0),
            "last_seen_at": last_seen,
            "tool_count": probe.get("tool_count", 0),
            "findings": all_findings,
            "checked_at": now,
        }
        results.append(result)

        if status == "healthy":
            healthy += 1
        elif status == "degraded":
            degraded += 1
        else:
            unreachable += 1

    if fmt == "json":
        print(json.dumps({
            "config_path": str(config_path),
            "servers_checked": len(results),
            "healthy": healthy, "degraded": degraded, "unreachable": unreachable,
            "servers": results,
        }, indent=2))
    else:
        print(f"\nMCP Health Check — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 55)
        print(f"  Config: {config_path}")
        print(f"  {len(results)} servers | {healthy} healthy | {degraded} degraded | {unreachable} unreachable")
        print()
        for r in results:
            if r["status"] == "healthy":
                icon = "+"
            elif r["status"] == "degraded":
                icon = "!"
            else:
                icon = "x"
            print(f"  {icon} [{r['status'].upper():>11}] {r['name']} ({r['transport']}) — {r['latency_ms']}ms")
            for f in r.get("findings", []):
                print(f"     [{f['severity']}] {f['check']}: {f['detail']}")
            print()

    # Persist
    state["last_check_at"] = now
    state["servers"] = results
    history = state.get("check_history") or []
    history.insert(0, {
        "checked_at": now, "servers_checked": len(results),
        "healthy": healthy, "degraded": degraded, "unreachable": unreachable,
    })
    state["check_history"] = history[:MAX_HISTORY]
    save_state(state)

    sys.exit(1 if unreachable > 0 else 0)


def cmd_config(fmt: str) -> None:
    config_path, config = find_mcp_config()
    if not config_path:
        print("No MCP configuration found.")
        sys.exit(1)

    servers = extract_servers(config)
    issues = []
    for server in servers:
        findings = validate_config_entry(server)
        if findings:
            issues.append({"server": server["name"], "findings": findings})

    if fmt == "json":
        print(json.dumps({
            "config_path": str(config_path),
            "servers": len(servers),
            "issues": issues,
        }, indent=2))
    else:
        print(f"\nMCP Config Validation — {config_path}")
        print("-" * 50)
        print(f"  {len(servers)} servers configured")
        print()
        if not issues:
            print("  All config entries valid.")
        else:
            for issue in issues:
                print(f"  ! {issue['server']}:")
                for f in issue["findings"]:
                    print(f"    [{f['severity']}] {f['detail']}")
        print()
        for server in servers:
            print(f"  {server['name']}: transport={server['transport']}", end="")
            if server.get("command"):
                print(f" cmd={server['command']}", end="")
            if server.get("url"):
                print(f" url={server['url']}", end="")
            print()


def cmd_status(state: dict) -> None:
    last = state.get("last_check_at", "never")
    print(f"\nMCP Health Checker — Last check: {last}")
    servers = state.get("servers") or []
    if servers:
        healthy = sum(1 for s in servers if s.get("status") == "healthy")
        degraded = sum(1 for s in servers if s.get("status") == "degraded")
        unreachable = sum(1 for s in servers if s.get("status") == "unreachable")
        print(f"  {len(servers)} servers | {healthy} healthy | {degraded} degraded | {unreachable} unreachable")
        for s in servers:
            icon = {"healthy": "+", "degraded": "!", "unreachable": "x"}.get(s.get("status", ""), "?")
            print(f"    {icon} {s['name']}: {s.get('status', 'unknown')} ({s.get('latency_ms', 0)}ms)")
    print()


def cmd_history(state: dict, fmt: str) -> None:
    history = state.get("check_history") or []
    if fmt == "json":
        print(json.dumps({"check_history": history}, indent=2))
    else:
        print(f"\nMCP Health Check History")
        print("-" * 50)
        if not history:
            print("  No check history yet.")
        else:
            for h in history[:10]:
                total = h.get("servers_checked", 0)
                healthy = h.get("healthy", 0)
                degraded = h.get("degraded", 0)
                unreachable = h.get("unreachable", 0)
                pct = round(healthy / total * 100) if total else 0
                ts = h.get("checked_at", "?")[:16]
                bar = "=" * (pct // 10) + "-" * (10 - pct // 10)
                print(f"  {ts}  [{bar}] {pct}% healthy  ({healthy}/{total})")
        print()


def main():
    parser = argparse.ArgumentParser(description="MCP Health Checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ping", action="store_true", help="Ping all configured MCP servers")
    group.add_argument("--config", action="store_true", help="Validate MCP config entries")
    group.add_argument("--status", action="store_true", help="Last check summary from state")
    group.add_argument("--history", action="store_true", help="Show past check results")
    parser.add_argument("--server", type=str, metavar="NAME", help="Check a specific server only")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds (default: 5)")
    parser.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE, help="Max connection age in hours (default: 24)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.ping:
        cmd_ping(state, args.server, args.timeout, args.max_age, args.format)
    elif args.config:
        cmd_config(args.format)
    elif args.status:
        cmd_status(state)
    elif args.history:
        cmd_history(state, args.format)


if __name__ == "__main__":
    main()
