#!/usr/bin/env python3
from __future__ import annotations

"""
Subagent Capability Auditor for openclaw-superpowers.

Audits subagent-related configuration for spawn depth, tool exposure, and
fleet shape before users trust multi-agent workflows.
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "subagent-capability-auditor" / "state.yaml"
MAX_HISTORY = 12
CONFIG_NAMES = {"agents.yaml", "agents.yml", "runtime.json", "openclaw.json", "config.yaml", "config.yml"}


def default_state() -> dict:
    return {
        "last_audit_at": "",
        "config_files": [],
        "findings": [],
        "audit_history": [],
    }


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


def finding(severity: str, check: str, detail: str, suggestion: str, file_path: Path | str = "") -> dict:
    return {
        "severity": severity,
        "check": check,
        "detail": detail,
        "suggestion": suggestion,
        "file_path": str(file_path),
        "detected_at": datetime.now().isoformat(),
        "resolved": False,
    }


def discover_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    matches = []
    for path in root.rglob("*"):
        if path.is_file() and path.name in CONFIG_NAMES:
            matches.append(path)
    return sorted(matches)


def parse_agent_count(text: str) -> int:
    match = re.search(r'agent[s]?\s*[:=]\s*\[', text, re.IGNORECASE)
    if match:
        return text.count("role:")
    return text.lower().count("role:")


def audit_files(files: list[Path]) -> list[dict]:
    findings = []
    if not files:
        findings.append(
            finding(
                "FAIL",
                "SUBAGENT_CONFIG_MISSING",
                "No candidate subagent config files were found.",
                "Point the auditor at the correct config root or add the relevant runtime config files.",
            )
        )
        return findings

    saw_spawn_tool = False
    saw_depth = False
    total_agents = 0

    for path in files:
        try:
            text = path.read_text(errors="replace")
        except Exception as exc:
            findings.append(
                finding(
                    "WARN",
                    "CONFIG_UNREADABLE",
                    f"Could not read config file: {exc}",
                    "Fix file permissions or path selection.",
                    path,
                )
            )
            continue

        total_agents += parse_agent_count(text)

        if "sessions_spawn" in text or "spawn_subagent" in text or "spawn-agent" in text:
            saw_spawn_tool = True

        depth_match = re.search(r'"?maxSpawnDepth"?\s*[:=]\s*(\d+)', text)
        if depth_match:
            saw_depth = True
            depth = int(depth_match.group(1))
            if depth < 1:
                findings.append(
                    finding(
                        "FAIL",
                        "SPAWN_DEPTH_INVALID",
                        f"maxSpawnDepth is {depth}.",
                        "Use a positive depth; 2 or 3 is a safer starting point.",
                        path,
                    )
                )
            elif depth == 1:
                findings.append(
                    finding(
                        "WARN",
                        "SPAWN_DEPTH_LOW",
                        "maxSpawnDepth is set to 1; deeper delegation will be blocked.",
                        "Raise maxSpawnDepth to 2 or 3 if nested delegation is expected.",
                        path,
                    )
                )
            elif depth > 3:
                findings.append(
                    finding(
                        "WARN",
                        "SPAWN_DEPTH_HIGH",
                        f"maxSpawnDepth is set to {depth}; runaway delegation becomes harder to reason about.",
                        "Lower maxSpawnDepth to 2 or 3 unless you have a strong reason to exceed it.",
                        path,
                    )
                )

        if ("agents:" in text or '"agents"' in text or "- name:" in text) and "role:" not in text and '"role"' not in text:
            findings.append(
                finding(
                    "WARN",
                    "ROLE_METADATA_MISSING",
                    "This config file does not show explicit agent roles.",
                    "Give agents distinct roles so fleet overlap stays manageable.",
                    path,
                )
            )

    if not saw_spawn_tool:
        findings.append(
            finding(
                "FAIL",
                "SPAWN_TOOL_MISSING",
                "No spawn tool exposure was detected in the scanned config.",
                "Expose `sessions_spawn` or the runtime's equivalent spawn capability before expecting subagents to work.",
            )
        )
    else:
        findings.append(
            finding(
                "INFO",
                "SPAWN_TOOL_PRESENT",
                "Spawn tooling appears to be exposed in the current configuration.",
                "No action required.",
            )
        )

    if not saw_depth:
        findings.append(
            finding(
                "WARN",
                "SPAWN_DEPTH_UNDECLARED",
                "No maxSpawnDepth setting was found in the scanned config.",
                "Declare a depth limit explicitly so delegation behaviour is predictable.",
            )
        )

    if total_agents >= 10:
        findings.append(
            finding(
                "WARN",
                "LARGE_AGENT_FLEET",
                f"Detected {total_agents} configured agents in a flat fleet.",
                "Consolidate overlapping roles or create stronger role boundaries before scaling further.",
            )
        )

    return findings


def print_summary(state: dict) -> None:
    findings = state.get("findings", [])
    fail_count = sum(1 for item in findings if item["severity"] == "FAIL")
    warn_count = sum(1 for item in findings if item["severity"] == "WARN")
    info_count = sum(1 for item in findings if item["severity"] == "INFO")
    print("\nSubagent Capability Auditor")
    print("───────────────────────────────────────────────────────")
    print(f"  {len(state.get('config_files', []))} config files | {fail_count} FAIL | {warn_count} WARN | {info_count} INFO")


def print_findings(state: dict) -> None:
    findings = state.get("findings", [])
    if not findings:
        print("\n  PASS  No findings.")
        return
    print("\nFindings")
    print("───────────────────────────────────────────────────────")
    for item in findings:
        print(f"  {item['severity']:4} {item['check']}")
        print(f"       {item['detail']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit subagent configuration safety")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit", action="store_true", help="Run the subagent capability audit")
    group.add_argument("--status", action="store_true", help="Show the last audit summary")
    group.add_argument("--findings", action="store_true", help="Show findings from the last audit")
    parser.add_argument("--path", default=str(OPENCLAW_DIR), help="Config root to inspect")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    if args.audit:
        root = Path(args.path).expanduser().resolve()
        files = discover_files(root)
        findings = audit_files(files)
        now = datetime.now().isoformat()
        state = {
            "last_audit_at": now,
            "config_files": [str(path) for path in files],
            "findings": findings,
            "audit_history": [],
        }
        previous = load_state()
        history = previous.get("audit_history") or []
        history.insert(
            0,
            {
                "audited_at": now,
                "fail_count": sum(1 for item in findings if item["severity"] == "FAIL"),
                "warn_count": sum(1 for item in findings if item["severity"] == "WARN"),
                "info_count": sum(1 for item in findings if item["severity"] == "INFO"),
                "file_count": len(files),
            },
        )
        state["audit_history"] = history[:MAX_HISTORY]
        save_state(state)
    else:
        state = load_state()

    if args.format == "json":
        print(json.dumps(state, indent=2))
        return

    print_summary(state)
    if args.findings or args.audit:
        print_findings(state)


if __name__ == "__main__":
    main()
