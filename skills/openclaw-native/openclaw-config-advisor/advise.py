#!/usr/bin/env python3
"""
Read-only OpenClaw config advisor.

Scans likely OpenClaw config files for provider, fallback, channel, MCP, and
gateway hints. Writes only its own state file under OPENCLAW_HOME.
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path


OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_HOME / "skill-state" / "openclaw-config-advisor" / "state.yaml"
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".env", ".conf"}
SECRET_RE = re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^'\"\s]+)", re.I)
MAX_FILES = 80
MAX_BYTES = 512_000


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_state() -> dict:
    return {
        "last_scan_at": "",
        "config_dir": "",
        "findings": [],
        "affected_areas": [],
        "scan_history": [],
    }


def load_state() -> dict:
    if not STATE_FILE.exists():
        return default_state()
    try:
        data = json.loads(STATE_FILE.read_text())
        if isinstance(data, dict):
            return {**default_state(), **data}
    except Exception:
        pass
    return default_state()


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def finding(severity: str, area: str, message: str, file_path=None) -> dict:
    return {
        "severity": severity,
        "area": area,
        "file": str(file_path) if file_path else "",
        "message": message,
    }


def candidate_files(config_dir: Path) -> list[Path]:
    if config_dir.is_file():
        return [config_dir]
    files = []
    for path in config_dir.rglob("*"):
        if len(files) >= MAX_FILES:
            break
        if path.is_file() and path.suffix.lower() in CONFIG_EXTS:
            try:
                if path.stat().st_size <= MAX_BYTES:
                    files.append(path)
            except OSError:
                continue
    return files


def read_file(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def scan_config(config_dir: Path) -> dict:
    findings = []
    scanned_at = now()

    if not config_dir.exists():
        findings.append(finding(
            "WARN",
            "config",
            "Config path does not exist; check OPENCLAW_HOME or pass --config-dir.",
            config_dir,
        ))
        return build_scan_result(scanned_at, config_dir, findings)

    files = candidate_files(config_dir)
    if not files:
        findings.append(finding(
            "WARN",
            "config",
            "No readable config files found under the config path.",
            config_dir,
        ))
        return build_scan_result(scanned_at, config_dir, findings)

    combined = "\n".join(read_file(path).lower() for path in files)
    by_file = [(path, read_file(path)) for path in files]

    checks = [
        ("providers", ["provider", "openai", "anthropic", "openrouter", "model"], "No provider or model routing hints found."),
        ("fallback", ["fallback", "backup", "default_model", "default-model"], "No fallback model hint found."),
        ("channels", ["telegram", "discord", "slack", "whatsapp", "signal", "feishu", "lark"], "No channel configuration hints found."),
        ("mcp", ["mcp", "modelcontextprotocol", "server", "tool"], "No MCP/tool server hints found."),
        ("gateway", ["gateway", "host", "port", "listen", "log"], "No gateway host, port, or log hints found."),
    ]

    for area, keywords, warning in checks:
        if any(keyword in combined for keyword in keywords):
            matched_file = next((path for path, text in by_file if any(k in text.lower() for k in keywords)), files[0])
            findings.append(finding("INFO", area, f"Found {area} config hints.", matched_file))
        else:
            findings.append(finding("WARN", area, warning, config_dir))

    for path, text in by_file:
        if SECRET_RE.search(text):
            findings.append(finding(
                "INFO",
                "secrets",
                "Secret-like setting found; value was not printed. Confirm permissions and storage policy.",
                path,
            ))

    return build_scan_result(scanned_at, config_dir, findings)


def build_scan_result(scanned_at: str, config_dir: Path, findings: list[dict]) -> dict:
    affected = sorted({item["area"] for item in findings})
    warn_count = sum(1 for item in findings if item["severity"] == "WARN")
    return {
        "scanned_at": scanned_at,
        "config_dir": str(config_dir),
        "findings": findings,
        "affected_areas": affected,
        "summary": {
            "finding_count": len(findings),
            "warn_count": warn_count,
            "info_count": len(findings) - warn_count,
        },
    }


def record_scan(result: dict) -> dict:
    state = load_state()
    state["last_scan_at"] = result["scanned_at"]
    state["config_dir"] = result["config_dir"]
    state["findings"] = result["findings"]
    state["affected_areas"] = result["affected_areas"]
    history = state.get("scan_history") or []
    history.append({
        "scanned_at": result["scanned_at"],
        "config_dir": result["config_dir"],
        "finding_count": result["summary"]["finding_count"],
        "warn_count": result["summary"]["warn_count"],
    })
    state["scan_history"] = history[-10:]
    save_state(state)
    return state


def explain(topic: str) -> dict:
    notes = {
        "providers": "Check provider names, model identifiers, and API key references. Do not print secret values.",
        "fallback": "Fallback config should name the backup provider/model and the condition that triggers it.",
        "channels": "Channel config should include enabled channels, credentials by reference, and webhook or polling mode.",
        "mcp": "MCP config should declare each server transport, command or URL, and expected tool availability.",
        "gateway": "Gateway config should make host, port, logs, and process ownership easy to inspect.",
    }
    key = topic.lower()
    return {"topic": topic, "guidance": notes.get(key, "Known topics: providers, fallback, channels, mcp, gateway.")}


def print_text(payload: dict) -> None:
    if "guidance" in payload:
        print(f"{payload['topic']}: {payload['guidance']}")
        return
    findings = payload.get("findings", [])
    print("OpenClaw Config Advisor")
    print(f"Config: {payload.get('config_dir', 'unknown')}")
    print(f"Findings: {len(findings)}")
    for item in findings:
        location = f" ({item['file']})" if item.get("file") else ""
        print(f"- {item['severity']} {item['area']}: {item['message']}{location}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OpenClaw config advisor.")
    parser.add_argument("--scan", action="store_true", help="Scan config files and write advisor state.")
    parser.add_argument("--status", action="store_true", help="Show the last advisor state.")
    parser.add_argument("--explain", metavar="TOPIC", help="Explain a config area.")
    parser.add_argument("--config-dir", default=str(OPENCLAW_HOME), help="OpenClaw config path to scan.")
    parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.explain:
        payload = explain(args.explain)
    elif args.scan:
        result = scan_config(Path(args.config_dir).expanduser())
        record_scan(result)
        payload = result
    else:
        payload = load_state()

    if args.output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
