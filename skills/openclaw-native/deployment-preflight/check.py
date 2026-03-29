#!/usr/bin/env python3
from __future__ import annotations

"""
Deployment Preflight for openclaw-superpowers.

Checks OpenClaw deployment safety before install, upgrade, or unattended use.
It focuses on runtime paths, workspace visibility, Docker/compose persistence,
and obvious gateway exposure mistakes.

Usage:
    python3 check.py --check
    python3 check.py --check --path /srv/openclaw
    python3 check.py --status
    python3 check.py --findings
    python3 check.py --format json
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "deployment-preflight" / "state.yaml"
WORKSPACE_DIR = Path(os.environ.get("OPENCLAW_WORKSPACE", OPENCLAW_DIR / "workspace"))
SUPERPOWERS_PATH = OPENCLAW_DIR / "extensions" / "superpowers"
MAX_HISTORY = 12
COMPOSE_NAMES = (
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
)
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".conf", ".ini"}
PUBLIC_PORT_RE = re.compile(r'(^|["\'\s-])((?:0\.0\.0\.0:)?(?:18789|3000|8080):(?:18789|3000|8080))')
LOOPBACK_PORT_RE = re.compile(r'127\.0\.0\.1:(?:18789|3000|8080):(?:18789|3000|8080)')
PUBLIC_BIND_RE = re.compile(r'0\.0\.0\.0|ws://0\.0\.0\.0|http://0\.0\.0\.0')


def default_state() -> dict:
    return {
        "last_check_at": "",
        "deployment_root": "",
        "deployment_mode": "unknown",
        "environment": {},
        "findings": [],
        "check_history": [],
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


def docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def detect_deployment_files(root: Path) -> tuple[str, list[Path]]:
    if not root.exists() or not root.is_dir():
        return "unknown", []

    compose_files = [root / name for name in COMPOSE_NAMES if (root / name).exists()]
    if compose_files:
        return "docker-compose", compose_files

    dockerfiles = [path for path in root.iterdir() if path.is_file() and path.name.startswith("Dockerfile")]
    if dockerfiles:
        return "dockerfile", dockerfiles

    return "local", []


def check_runtime_paths() -> list[dict]:
    items = []

    if not OPENCLAW_DIR.exists():
        items.append(
            finding(
                "FAIL",
                "OPENCLAW_HOME_MISSING",
                f"OpenClaw home does not exist: {OPENCLAW_DIR}",
                "Create or mount OPENCLAW_HOME before deployment.",
                OPENCLAW_DIR,
            )
        )
        return items

    if not os.access(str(OPENCLAW_DIR), os.W_OK):
        items.append(
            finding(
                "FAIL",
                "OPENCLAW_HOME_UNWRITABLE",
                f"OpenClaw home is not writable: {OPENCLAW_DIR}",
                "Fix filesystem permissions or container user mapping.",
                OPENCLAW_DIR,
            )
        )

    state_dir = OPENCLAW_DIR / "skill-state"
    if not state_dir.exists():
        items.append(
            finding(
                "WARN",
                "STATE_DIR_MISSING",
                f"Skill state directory does not exist yet: {state_dir}",
                "Run ./install.sh or create the directory before enabling stateful skills.",
                state_dir,
            )
        )

    if not WORKSPACE_DIR.exists():
        items.append(
            finding(
                "WARN",
                "WORKSPACE_MISSING",
                f"Workspace directory does not exist: {WORKSPACE_DIR}",
                "Mount or create the workspace before trusting project memory or identity files.",
                WORKSPACE_DIR,
            )
        )
    else:
        required = ["AGENTS.md", "SOUL.md", "MEMORY.md"]
        present = [name for name in required if (WORKSPACE_DIR / name).exists()]
        missing = [name for name in required if not (WORKSPACE_DIR / name).exists()]
        if not present:
            items.append(
                finding(
                    "WARN",
                    "WORKSPACE_BOOTSTRAP_MISSING",
                    "Workspace exists but none of AGENTS.md, SOUL.md, or MEMORY.md were found.",
                    "Add the bootstrap files the agent depends on before unattended use.",
                    WORKSPACE_DIR,
                )
            )
        elif missing:
            items.append(
                finding(
                    "WARN",
                    "WORKSPACE_BOOTSTRAP_PARTIAL",
                    f"Workspace exists but {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing.",
                    "Add the missing bootstrap files before relying on persistent context.",
                    WORKSPACE_DIR,
                )
            )

    if not SUPERPOWERS_PATH.exists():
        items.append(
            finding(
                "WARN",
                "SUPERPOWERS_NOT_INSTALLED",
                f"superpowers is not installed at {SUPERPOWERS_PATH}",
                "Run ./install.sh after cloning the repository outside the extensions directory.",
                SUPERPOWERS_PATH,
            )
        )
    elif SUPERPOWERS_PATH.is_symlink():
        items.append(
            finding(
                "INFO",
                "SUPERPOWERS_SYMLINK",
                "superpowers is installed as a symlink to the skills directory.",
                "No action required.",
                SUPERPOWERS_PATH,
            )
        )
    else:
        items.append(
            finding(
                "WARN",
                "SUPERPOWERS_NOT_SYMLINK",
                "superpowers exists but is not a symlink.",
                "Confirm this is intentional and not a stale checkout inside the extensions directory.",
                SUPERPOWERS_PATH,
            )
        )

    return items


def check_tooling(mode: str) -> list[dict]:
    items = []
    docker_found = shutil.which("docker") is not None
    docker_compose_found = docker_compose_available()

    if shutil.which("openclaw") is None:
        items.append(
            finding(
                "WARN",
                "OPENCLAW_CLI_MISSING",
                "`openclaw` CLI is not on PATH.",
                "Install the OpenClaw CLI in the runtime environment.",
            )
        )
    if not HAS_YAML:
        items.append(
            finding(
                "WARN",
                "PYYAML_MISSING",
                "PyYAML is unavailable; some stateful helpers will degrade.",
                "Install PyYAML with `python3 -m pip install PyYAML`.",
            )
        )
    if mode in {"docker-compose", "dockerfile"} and not docker_found:
        items.append(
            finding(
                "WARN",
                "DOCKER_MISSING",
                "Deployment files suggest Docker, but `docker` is not on PATH.",
                "Run the checker where Docker is installed or point it at the correct environment.",
            )
        )
    if mode == "docker-compose" and docker_found and not docker_compose_found:
        items.append(
            finding(
                "WARN",
                "DOCKER_COMPOSE_MISSING",
                "Docker is installed, but `docker compose` is unavailable.",
                "Install the compose plugin or run the checker where compose is available.",
            )
        )
    return items


def check_compose_files(files: list[Path]) -> list[dict]:
    items = []
    for path in files:
        try:
            text = path.read_text()
        except Exception as exc:
            items.append(
                finding(
                    "WARN",
                    "COMPOSE_UNREADABLE",
                    f"Could not read compose file: {exc}",
                    "Fix file permissions or path selection before relying on preflight output.",
                    path,
                )
            )
            continue

        if ".openclaw" not in text:
            items.append(
                finding(
                    "WARN",
                    "EPHEMERAL_OPENCLAW_HOME",
                    f"{path.name} does not appear to mount `.openclaw`.",
                    "Persist OPENCLAW_HOME so skills, memory, and config survive container restarts.",
                    path,
                )
            )

        if "/workspace" not in text and "workspace" not in text:
            items.append(
                finding(
                    "WARN",
                    "WORKSPACE_MOUNT_UNCLEAR",
                    f"{path.name} does not clearly mount a workspace path.",
                    "Confirm the runtime can see the project workspace and bootstrap files.",
                    path,
                )
            )

        if "network_mode: host" in text:
            items.append(
                finding(
                    "WARN",
                    "HOST_NETWORK_MODE",
                    f"{path.name} uses `network_mode: host`.",
                    "Prefer explicit loopback bindings unless host networking is required.",
                    path,
                )
            )

        if PUBLIC_PORT_RE.search(text) and not LOOPBACK_PORT_RE.search(text):
            items.append(
                finding(
                    "WARN",
                    "PUBLIC_GATEWAY_PORT",
                    f"{path.name} publishes a common OpenClaw port without loopback binding.",
                    "Bind the gateway to 127.0.0.1 or put it behind an authenticated reverse proxy.",
                    path,
                )
            )
    return items


def check_config_exposure() -> list[dict]:
    items = []
    if not OPENCLAW_DIR.exists():
        return items

    scanned = 0
    for path in OPENCLAW_DIR.rglob("*"):
        if not path.is_file() or path.suffix not in CONFIG_EXTENSIONS:
            continue
        scanned += 1
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue

        if PUBLIC_BIND_RE.search(text):
            items.append(
                finding(
                    "WARN",
                    "PUBLIC_BIND_ADDRESS",
                    f"{path.name} appears to bind OpenClaw services to 0.0.0.0.",
                    "Use loopback bindings unless you have an authenticated proxy in front.",
                    path,
                )
            )
    return items[:10]


def run_check(root: Path) -> dict:
    mode, deployment_files = detect_deployment_files(root)
    findings = []
    if not root.exists() or not root.is_dir():
        findings.append(
            finding(
                "FAIL",
                "DEPLOYMENT_ROOT_MISSING",
                f"Deployment root does not exist or is not a directory: {root}",
                "Point `--path` at the directory containing your compose or Docker files.",
                root,
            )
        )
    findings.extend(check_runtime_paths())
    findings.extend(check_tooling(mode))
    if mode == "docker-compose":
        findings.extend(check_compose_files(deployment_files))
    findings.extend(check_config_exposure())

    fail_count = sum(1 for item in findings if item["severity"] == "FAIL")
    warn_count = sum(1 for item in findings if item["severity"] == "WARN")
    info_count = sum(1 for item in findings if item["severity"] == "INFO")
    environment = {
        "openclaw_home": str(OPENCLAW_DIR),
        "workspace_dir": str(WORKSPACE_DIR),
        "superpowers_path": str(SUPERPOWERS_PATH),
        "openclaw_cli_found": shutil.which("openclaw") is not None,
        "pyyaml_found": HAS_YAML,
        "docker_found": shutil.which("docker") is not None,
        "docker_compose_found": docker_compose_available(),
        "files_checked": len(deployment_files),
    }

    state = load_state()
    history = state.get("check_history") or []
    now = datetime.now().isoformat()
    history.insert(
        0,
        {
            "checked_at": now,
            "deployment_mode": mode,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "info_count": info_count,
            "files_checked": len(deployment_files),
        },
    )

    report = {
        "last_check_at": now,
        "deployment_root": str(root),
        "deployment_mode": mode,
        "environment": environment,
        "findings": findings,
        "check_history": history[:MAX_HISTORY],
    }
    save_state(report)
    return report


def print_summary(report: dict) -> None:
    findings = report.get("findings", [])
    fail_count = sum(1 for item in findings if item["severity"] == "FAIL")
    warn_count = sum(1 for item in findings if item["severity"] == "WARN")
    info_count = sum(1 for item in findings if item["severity"] == "INFO")
    print("\nDeployment Preflight")
    print("───────────────────────────────────────────────────────")
    print(f"  Mode: {report.get('deployment_mode', 'unknown')}")
    print(f"  Root: {report.get('deployment_root', '')}")
    print(f"  Files checked: {report.get('environment', {}).get('files_checked', 0)}")
    print(f"  {fail_count} FAIL | {warn_count} WARN | {info_count} INFO")


def print_findings(report: dict) -> None:
    findings = report.get("findings", [])
    if not findings:
        print("\n  PASS  No deployment findings.")
        return
    print("\nFindings")
    print("───────────────────────────────────────────────────────")
    for item in findings:
        print(f"  {item['severity']:4} {item['check']}")
        print(f"       {item['detail']}")
        if item["file_path"]:
            print(f"       File: {item['file_path']}")


def print_status(report: dict) -> None:
    print_summary(report)
    history = report.get("check_history", [])
    if history:
        print("\nRecent checks")
        print("───────────────────────────────────────────────────────")
        for item in history[:5]:
            print(
                f"  {item['checked_at'][:19]}  "
                f"{item['deployment_mode']}  "
                f"F:{item['fail_count']} W:{item['warn_count']} I:{item['info_count']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deployment safety checks for OpenClaw")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Run a deployment preflight")
    group.add_argument("--status", action="store_true", help="Show the last preflight summary")
    group.add_argument("--findings", action="store_true", help="Show findings from the last preflight")
    parser.add_argument("--path", default=".", help="Deployment root containing compose or Docker files")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    if args.check:
        report = run_check(Path(args.path).expanduser().resolve())
    else:
        report = load_state()

    if args.format == "json":
        print(json.dumps(report, indent=2))
        return

    if args.status:
        print_status(report)
        return

    print_summary(report)
    print_findings(report)
    if args.check:
        fail_count = sum(1 for item in report.get("findings", []) if item["severity"] == "FAIL")
        sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
