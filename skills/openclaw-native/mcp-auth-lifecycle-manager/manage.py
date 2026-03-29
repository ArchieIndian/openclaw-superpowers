#!/usr/bin/env python3
from __future__ import annotations

"""
MCP Auth Lifecycle Manager for openclaw-superpowers.

Tracks MCP auth expiry, missing env vars, refresh readiness, and refresh history.
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "mcp-auth-lifecycle-manager" / "state.yaml"
MAX_HISTORY = 20

MCP_CONFIG_PATHS = [
    OPENCLAW_DIR / "config" / "mcp.yaml",
    OPENCLAW_DIR / "config" / "mcp.json",
    OPENCLAW_DIR / "mcp.yaml",
    OPENCLAW_DIR / "mcp.json",
    Path.home() / ".config" / "openclaw" / "mcp.yaml",
    Path.home() / ".config" / "openclaw" / "mcp.json",
]

AUTH_REGISTRY_PATHS = [
    OPENCLAW_DIR / "config" / "mcp-auth.yaml",
    OPENCLAW_DIR / "config" / "mcp-auth.json",
    OPENCLAW_DIR / "mcp-auth.yaml",
    OPENCLAW_DIR / "mcp-auth.json",
    Path.home() / ".config" / "openclaw" / "mcp-auth.yaml",
    Path.home() / ".config" / "openclaw" / "mcp-auth.json",
]

SECRET_KEY_PATTERN = re.compile(r"(token|secret|password|api[_-]?key|authorization)", re.I)
ENV_REF_PATTERN = re.compile(r"^\$(\w+)$|^\$\{(\w+)\}$")


def default_state() -> dict:
    return {
        "last_scan_at": "",
        "last_config_path": "",
        "last_registry_path": "",
        "servers": [],
        "refresh_history": [],
    }


def load_structured(path: Path) -> dict:
    text = path.read_text()
    if path.suffix == ".json":
        return json.loads(text)
    if HAS_YAML:
        return yaml.safe_load(text) or {}
    return {}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return default_state()
    try:
        text = STATE_FILE.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or default_state()
        return json.loads(text)
    except Exception:
        return default_state()


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as handle:
            yaml.dump(state, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        STATE_FILE.write_text(json.dumps(state, indent=2))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def find_config(paths: list[Path]) -> tuple[Path | None, dict]:
    for path in paths:
        if not path.exists():
            continue
        try:
            return path, load_structured(path)
        except Exception:
            continue
    return None, {}


def extract_servers(config: dict) -> list[dict]:
    servers = []
    mcp_servers = config.get("mcpServers") or config.get("servers") or config
    if not isinstance(mcp_servers, dict):
        return servers
    for name, definition in mcp_servers.items():
        if isinstance(definition, dict):
            servers.append({"name": name, "definition": definition})
    return servers


def extract_registry_entry(registry: dict, name: str) -> dict:
    if not isinstance(registry, dict):
        return {}
    servers = registry.get("servers") or registry
    if isinstance(servers, dict):
        entry = servers.get(name)
        if isinstance(entry, dict):
            return entry
    return {}


def get_existing_server(state: dict, name: str) -> dict:
    for item in state.get("servers", []):
        if item.get("name") == name:
            return item
    return {}


def detect_auth_type(definition: dict, registry_entry: dict) -> str:
    explicit = registry_entry.get("auth_type")
    if explicit:
        return str(explicit)
    env_map = definition.get("env") if isinstance(definition.get("env"), dict) else {}
    combined = " ".join(str(v) for v in definition.values())
    if any(SECRET_KEY_PATTERN.search(key) for key in env_map):
        return "env-token"
    if "oauth" in combined.lower() or "pkce" in combined.lower():
        return "oauth"
    if SECRET_KEY_PATTERN.search(combined):
        return "bearer"
    return "none"


def extract_env_vars(definition: dict) -> tuple[list[str], list[str], int]:
    env_vars: list[str] = []
    missing: list[str] = []
    literal_secrets = 0
    env_map = definition.get("env") if isinstance(definition.get("env"), dict) else {}
    for key, value in env_map.items():
        value_str = str(value)
        match = ENV_REF_PATTERN.match(value_str.strip())
        if match:
            env_name = match.group(1) or match.group(2) or key
            env_vars.append(env_name)
            if not os.environ.get(env_name):
                missing.append(env_name)
        elif SECRET_KEY_PATTERN.search(key) or SECRET_KEY_PATTERN.search(value_str):
            literal_secrets += 1
    return sorted(set(env_vars)), sorted(set(missing)), literal_secrets


def count_literal_secrets(value) -> int:
    if isinstance(value, dict):
        total = 0
        for key, nested in value.items():
            if isinstance(nested, str) and SECRET_KEY_PATTERN.search(str(key)) and not ENV_REF_PATTERN.match(nested.strip()):
                total += 1
            total += count_literal_secrets(nested)
        return total
    if isinstance(value, list):
        return sum(count_literal_secrets(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        if value.startswith("Bearer ") or ("token" in lowered and not ENV_REF_PATTERN.match(value.strip())):
            return 1
    return 0


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_findings(server: dict) -> list[dict]:
    findings: list[dict] = []
    for env_name in server.get("missing_env_vars", []):
        findings.append(
            {
                "check": "TOKEN_MISSING",
                "severity": "CRITICAL",
                "detail": f"Missing environment variable: {env_name}",
            }
        )

    expires_at = parse_time(server.get("expires_at", ""))
    if expires_at is not None:
        delta = expires_at - datetime.now()
        if delta.total_seconds() <= 0:
            findings.append(
                {
                    "check": "TOKEN_EXPIRED",
                    "severity": "CRITICAL",
                    "detail": f"Auth expired at {server['expires_at']}",
                }
            )
        elif delta <= timedelta(hours=24):
            findings.append(
                {
                    "check": "TOKEN_EXPIRING",
                    "severity": "HIGH",
                    "detail": f"Auth expires in {int(delta.total_seconds() // 3600)}h",
                }
            )

    auth_type = server.get("auth_type", "none")
    if auth_type != "none" and not server.get("refresh_command") and not server.get("notes"):
        findings.append(
            {
                "check": "REFRESH_UNDEFINED",
                "severity": "HIGH",
                "detail": "No refresh command or documented recovery path",
            }
        )

    last_refresh = parse_time(server.get("last_refresh_at", ""))
    interval_hours = int(server.get("refresh_interval_hours", 0) or 0)
    if interval_hours > 0 and last_refresh is not None:
        age_hours = (datetime.now() - last_refresh).total_seconds() / 3600
        if age_hours > interval_hours:
            findings.append(
                {
                    "check": "REFRESH_OVERDUE",
                    "severity": "HIGH",
                    "detail": f"Last successful refresh was {int(age_hours)}h ago (interval: {interval_hours}h)",
                }
            )

    if int(server.get("literal_secret_count", 0) or 0) > 0:
        findings.append(
            {
                "check": "STATIC_SECRET_IN_CONFIG",
                "severity": "HIGH",
                "detail": "Token-like material appears to be hardcoded in MCP config",
            }
        )

    if server.get("interactive_refresh"):
        findings.append(
            {
                "check": "INTERACTIVE_REFRESH",
                "severity": "MEDIUM",
                "detail": "Refresh still requires a manual browser login",
            }
        )

    return findings


def compute_status(findings: list[dict]) -> str:
    severities = {item.get("severity") for item in findings}
    if "CRITICAL" in severities:
        return "critical"
    if "HIGH" in severities or "MEDIUM" in severities:
        return "degraded"
    return "healthy"


def scan_servers(state: dict, server_filter: str | None = None) -> dict:
    config_path, config = find_config(MCP_CONFIG_PATHS)
    registry_path, registry = find_config(AUTH_REGISTRY_PATHS)

    scanned = []
    for server in extract_servers(config):
        name = server["name"]
        if server_filter and name != server_filter:
            continue
        definition = server["definition"]
        registry_entry = extract_registry_entry(registry, name)
        existing = get_existing_server(state, name)
        env_vars, missing_env_vars, literal_from_env = extract_env_vars(definition)
        literal_secrets = literal_from_env + count_literal_secrets(definition)
        entry = {
            "name": name,
            "provider": registry_entry.get("provider", name),
            "auth_type": detect_auth_type(definition, registry_entry),
            "env_vars": env_vars,
            "missing_env_vars": missing_env_vars,
            "expires_at": str(registry_entry.get("expires_at", existing.get("expires_at", "")) or ""),
            "last_refresh_at": str(existing.get("last_refresh_at", registry_entry.get("last_refresh_at", "")) or ""),
            "refresh_interval_hours": int(
                registry_entry.get("refresh_interval_hours", existing.get("refresh_interval_hours", 0)) or 0
            ),
            "interactive_refresh": bool(
                registry_entry.get("interactive_refresh", existing.get("interactive_refresh", False))
            ),
            "refresh_command": str(registry_entry.get("refresh_command", existing.get("refresh_command", "")) or ""),
            "notes": str(registry_entry.get("notes", existing.get("notes", "")) or ""),
            "literal_secret_count": literal_secrets,
        }
        entry["findings"] = build_findings(entry)
        entry["status"] = compute_status(entry["findings"]) if entry["auth_type"] != "none" else "unknown"
        scanned.append(entry)

    if server_filter:
        existing = {item.get("name"): item for item in state.get("servers", []) if item.get("name")}
        for item in scanned:
            existing[item["name"]] = item
        scanned = list(existing.values())

    scanned.sort(key=lambda item: item["name"])
    state["last_scan_at"] = now_iso()
    state["last_config_path"] = str(config_path or "")
    state["last_registry_path"] = str(registry_path or "")
    state["servers"] = scanned
    return state


def record_refresh(state: dict, server_name: str, result: str, note: str, expires_at: str) -> dict:
    servers = state.get("servers", [])
    server = next((item for item in servers if item.get("name") == server_name), None)
    if server is None:
        server = {
            "name": server_name,
            "provider": server_name,
            "auth_type": "unknown",
            "status": "unknown",
            "env_vars": [],
            "missing_env_vars": [],
            "expires_at": "",
            "last_refresh_at": "",
            "refresh_interval_hours": 0,
            "interactive_refresh": False,
            "refresh_command": "",
            "notes": "",
            "findings": [],
        }
        servers.append(server)

    recorded_at = now_iso()
    history = state.get("refresh_history") or []
    history.insert(
        0,
        {
            "recorded_at": recorded_at,
            "server": server_name,
            "result": result,
            "note": note,
            "expires_at": expires_at,
        },
    )
    state["refresh_history"] = history[:MAX_HISTORY]

    if result == "success":
        server["last_refresh_at"] = recorded_at
        if expires_at:
            server["expires_at"] = expires_at

    server["findings"] = build_findings(server)
    server["status"] = compute_status(server["findings"]) if server.get("auth_type") != "none" else "unknown"
    return state


def print_scan(state: dict) -> None:
    servers = state.get("servers", [])
    healthy = sum(1 for item in servers if item.get("status") == "healthy")
    degraded = sum(1 for item in servers if item.get("status") == "degraded")
    critical = sum(1 for item in servers if item.get("status") == "critical")

    print("\nMCP Auth Lifecycle Manager")
    print("───────────────────────────────────────────────────────")
    print(f"  {len(servers)} servers | {healthy} healthy | {degraded} degraded | {critical} critical")
    if state.get("last_config_path"):
        print(f"  Config: {state['last_config_path']}")
    if state.get("last_registry_path"):
        print(f"  Registry: {state['last_registry_path']}")
    if not servers:
        print("\n  No MCP servers discovered.")
        return
    for item in servers:
        print(f"  {item['status'].upper():9} {item['name']}  {item['auth_type']}")
        for finding in item.get("findings", [])[:3]:
            print(f"    [{finding['severity']}] {finding['check']}: {finding['detail']}")


def print_status(state: dict) -> None:
    print(f"\nMCP Auth Lifecycle Manager — Last scan: {state.get('last_scan_at') or 'never'}")
    print("───────────────────────────────────────────────────────")
    servers = state.get("servers", [])
    if not servers:
        print("  No auth state recorded.")
        return
    for item in servers:
        expiry = item.get("expires_at") or "n/a"
        refresh = item.get("last_refresh_at") or "never"
        print(f"  {item['name']}: {item['status']}  expires={expiry}  refreshed={refresh}")


def print_history(state: dict) -> None:
    history = state.get("refresh_history", [])
    print("\nMCP Auth Refresh History")
    print("───────────────────────────────────────────────────────")
    if not history:
        print("  No refresh events recorded.")
        return
    for item in history[:10]:
        print(f"  {item['recorded_at']}  {item['server']}  {item['result']}  {item['note']}")


def print_plan(state: dict, server_name: str) -> None:
    server = next((item for item in state.get("servers", []) if item.get("name") == server_name), None)
    if server is None:
        raise SystemExit(f"No auth record found for server '{server_name}'")
    print(f"\nRefresh plan for {server_name}")
    print("───────────────────────────────────────────────────────")
    if server.get("env_vars"):
        print(f"1. Confirm env vars: {', '.join(server['env_vars'])}")
    else:
        print("1. Confirm auth inputs are available to the MCP process.")
    if server.get("refresh_command"):
        print(f"2. Run: {server['refresh_command']}")
    else:
        print("2. Follow the documented provider refresh flow or update the registry with refresh_command.")
    print("3. Re-run mcp-health-checker to confirm the server still initializes cleanly.")
    print(f"4. Record the result with: python3 manage.py --record-refresh {server_name} --result success")
    if server.get("interactive_refresh"):
        print("5. This server still requires an interactive login; do not rely on it for unattended workloads.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track MCP auth expiry and refresh readiness")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Scan MCP auth dependencies and refresh readiness")
    group.add_argument("--status", action="store_true", help="Show last recorded auth status")
    group.add_argument("--history", action="store_true", help="Show refresh history")
    group.add_argument("--plan", metavar="SERVER", help="Print refresh steps for a server")
    group.add_argument("--record-refresh", metavar="SERVER", help="Record a refresh outcome for a server")
    parser.add_argument("--server", help="Optional single-server filter for --scan")
    parser.add_argument("--result", choices=["success", "failed"], help="Refresh result for --record-refresh")
    parser.add_argument("--note", default="", help="Context or command used during refresh")
    parser.add_argument("--expires-at", default="", help="Updated auth expiry for successful refreshes")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    state = load_state()

    if args.scan:
        state = scan_servers(state, args.server)
        save_state(state)
    elif args.record_refresh:
        if not args.result:
            raise SystemExit("--result is required for --record-refresh")
        state = record_refresh(state, args.record_refresh, args.result, args.note, args.expires_at)
        save_state(state)

    if args.format == "json":
        print(json.dumps(state, indent=2))
        return

    if args.scan:
        print_scan(state)
    elif args.status:
        print_status(state)
    elif args.history:
        print_history(state)
    elif args.plan:
        print_plan(state, args.plan)
    elif args.record_refresh:
        print_status(state)


if __name__ == "__main__":
    main()
