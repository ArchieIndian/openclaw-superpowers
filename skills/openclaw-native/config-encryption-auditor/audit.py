#!/usr/bin/env python3
"""
Config Encryption Auditor for openclaw-superpowers.

Scans OpenClaw config directories for plaintext API keys, tokens,
and secrets in unencrypted files.

Usage:
    python3 audit.py --scan
    python3 audit.py --scan --critical-only
    python3 audit.py --fix-permissions
    python3 audit.py --suggest-env
    python3 audit.py --status
    python3 audit.py --format json
"""

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "config-encryption-auditor" / "state.yaml"
MAX_HISTORY = 12

# Scan these directories for config files
SCAN_DIRS = [OPENCLAW_DIR]
SCAN_EXTENSIONS = {".yaml", ".yml", ".json", ".toml", ".env", ".conf", ".cfg", ".ini"}

# ── Secret patterns ───────────────────────────────────────────────────────────

API_KEY_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), "OpenAI/Anthropic API key"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID"),
    (re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}'), "GitHub token"),
    (re.compile(r'xoxb-[0-9A-Za-z\-]{50,}'), "Slack bot token"),
    (re.compile(r'xoxp-[0-9A-Za-z\-]{50,}'), "Slack user token"),
    (re.compile(r'[0-9]+:AA[A-Za-z0-9_-]{33}'), "Telegram bot token"),
    (re.compile(r'AIza[0-9A-Za-z_-]{35}'), "Google API key"),
    (re.compile(r'sk_live_[0-9a-zA-Z]{24,}'), "Stripe secret key"),
]

TOKEN_PATTERNS = [
    (re.compile(r'(?:token|secret|password|passwd|pwd|apikey|api_key)\s*[:=]\s*["\']?[A-Za-z0-9_\-\.]{8,}', re.I),
     "Generic secret assignment"),
    (re.compile(r'Bearer [A-Za-z0-9\-_\.]{20,}'), "Bearer token"),
    (re.compile(r'Basic [A-Za-z0-9+/=]{20,}'), "Basic auth credential"),
]

# Environment variable mapping suggestions
ENV_SUGGESTIONS = {
    "anthropic": "OPENCLAW_ANTHROPIC_API_KEY",
    "openai": "OPENCLAW_OPENAI_API_KEY",
    "slack": "OPENCLAW_SLACK_TOKEN",
    "telegram": "OPENCLAW_TELEGRAM_TOKEN",
    "discord": "OPENCLAW_DISCORD_TOKEN",
    "github": "OPENCLAW_GITHUB_TOKEN",
    "stripe": "OPENCLAW_STRIPE_KEY",
    "aws": "OPENCLAW_AWS_ACCESS_KEY",
}


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"findings": [], "audit_history": []}
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


# ── Scanning ──────────────────────────────────────────────────────────────────

def scan_file(filepath: Path) -> list[dict]:
    findings = []
    now = datetime.now().isoformat()
    rel = str(filepath.relative_to(OPENCLAW_DIR)) if str(filepath).startswith(str(OPENCLAW_DIR)) else str(filepath)

    try:
        text = filepath.read_text(errors="replace")
    except (PermissionError, OSError):
        return findings

    # Check for API keys
    for pattern, label in API_KEY_PATTERNS:
        if pattern.search(text):
            findings.append({
                "file_path": rel, "check": "PLAINTEXT_API_KEY",
                "severity": "CRITICAL",
                "detail": f"Found {label} pattern in plaintext",
                "suggestion": f"Migrate to environment variable or encrypted vault.",
                "detected_at": now, "resolved": False,
            })

    # Check for tokens
    for pattern, label in TOKEN_PATTERNS:
        if pattern.search(text):
            findings.append({
                "file_path": rel, "check": "PLAINTEXT_TOKEN",
                "severity": "HIGH",
                "detail": f"Found {label} pattern in plaintext",
                "suggestion": "Use environment variables instead of inline credentials.",
                "detected_at": now, "resolved": False,
            })

    # Check file permissions (Unix only)
    try:
        mode = filepath.stat().st_mode
        if mode & stat.S_IROTH or mode & stat.S_IRGRP:
            findings.append({
                "file_path": rel, "check": "WORLD_READABLE",
                "severity": "HIGH",
                "detail": f"File permissions {oct(mode)[-3:]} — readable by other users",
                "suggestion": "Run: chmod 600 " + str(filepath),
                "detected_at": now, "resolved": False,
            })
    except (OSError, AttributeError):
        pass

    return findings


def scan_all(critical_only: bool = False) -> tuple[list, int]:
    all_findings = []
    files_scanned = 0
    now = datetime.now().isoformat()

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for filepath in scan_dir.rglob("*"):
            if not filepath.is_file():
                continue
            if filepath.suffix not in SCAN_EXTENSIONS:
                continue
            # Skip skill-state (our own state files)
            if "skill-state" in str(filepath):
                continue
            files_scanned += 1
            findings = scan_file(filepath)
            all_findings.extend(findings)

    # Check gitignore
    gitignore = Path.home() / ".gitignore"
    openclaw_gitignored = False
    if gitignore.exists():
        try:
            gi_text = gitignore.read_text()
            if ".openclaw" in gi_text or "openclaw" in gi_text:
                openclaw_gitignored = True
        except Exception:
            pass
    if not openclaw_gitignored:
        all_findings.append({
            "file_path": str(OPENCLAW_DIR), "check": "NO_GITIGNORE",
            "severity": "MEDIUM",
            "detail": "~/.openclaw not found in global .gitignore",
            "suggestion": "Add '.openclaw/' to ~/.gitignore to prevent accidental commits.",
            "detected_at": now, "resolved": False,
        })

    if critical_only:
        all_findings = [f for f in all_findings if f["severity"] == "CRITICAL"]

    return all_findings, files_scanned


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(state: dict, critical_only: bool, fmt: str) -> None:
    findings, files_scanned = scan_all(critical_only)
    now = datetime.now().isoformat()
    critical = sum(1 for f in findings if f["severity"] == "CRITICAL")
    high = sum(1 for f in findings if f["severity"] == "HIGH")
    medium = sum(1 for f in findings if f["severity"] == "MEDIUM")

    if fmt == "json":
        print(json.dumps({"files_scanned": files_scanned, "findings": findings}, indent=2))
    else:
        print(f"\nConfig Encryption Audit — {datetime.now().strftime('%Y-%m-%d')}")
        print("─" * 50)
        print(f"  {files_scanned} files scanned | "
              f"{critical} CRITICAL | {high} HIGH | {medium} MEDIUM")
        print()
        if not findings:
            print("  ✓ No exposed secrets detected.")
        else:
            for f in findings:
                icon = "✗" if f["severity"] == "CRITICAL" else ("!" if f["severity"] == "HIGH" else "⚠")
                print(f"  {icon} [{f['severity']}] {f['file_path']}: {f['check']}")
                print(f"     {f['detail']}")
                print(f"     → {f['suggestion']}")
                print()

    # Persist
    history = state.get("audit_history") or []
    history.insert(0, {
        "audited_at": now, "files_scanned": files_scanned,
        "critical_count": critical, "high_count": high, "medium_count": medium,
    })
    state["audit_history"] = history[:MAX_HISTORY]
    state["last_audit_at"] = now
    state["files_scanned"] = files_scanned
    state["findings"] = findings
    save_state(state)
    sys.exit(1 if critical > 0 else 0)


def cmd_fix_permissions(state: dict) -> None:
    fixed = 0
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for filepath in scan_dir.rglob("*"):
            if not filepath.is_file() or filepath.suffix not in SCAN_EXTENSIONS:
                continue
            if "skill-state" in str(filepath):
                continue
            try:
                mode = filepath.stat().st_mode
                if mode & stat.S_IROTH or mode & stat.S_IRGRP:
                    filepath.chmod(0o600)
                    print(f"  ✓ chmod 600: {filepath}")
                    fixed += 1
            except (OSError, AttributeError):
                pass
    print(f"\n✓ Fixed permissions on {fixed} files.")


def cmd_suggest_env() -> None:
    print("\nEnvironment Variable Migration Guide")
    print("─" * 48)
    print("Replace plaintext credentials in config files with environment variables:\n")
    for service, env_var in sorted(ENV_SUGGESTIONS.items()):
        print(f"  {service:12s} → export {env_var}=\"<your-key>\"")
    print(f"\nAdd these to your shell profile (~/.zshrc, ~/.bashrc) or a .env file.")
    print("OpenClaw reads OPENCLAW_* environment variables automatically.\n")


def cmd_status(state: dict) -> None:
    last = state.get("last_audit_at", "never")
    print(f"\nConfig Encryption Auditor — Last run: {last}")
    history = state.get("audit_history") or []
    if history:
        h = history[0]
        print(f"  {h.get('files_scanned',0)} files | "
              f"{h.get('critical_count',0)} CRITICAL | "
              f"{h.get('high_count',0)} HIGH | {h.get('medium_count',0)} MEDIUM")
    active = [f for f in (state.get("findings") or []) if not f.get("resolved")]
    if active:
        print(f"\n  Unresolved ({len(active)}):")
        for f in active[:3]:
            print(f"    [{f['severity']}] {f['file_path']}: {f['check']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Config Encryption Auditor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true")
    group.add_argument("--fix-permissions", action="store_true")
    group.add_argument("--suggest-env", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--critical-only", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.scan:
        cmd_scan(state, args.critical_only, args.format)
    elif args.fix_permissions:
        cmd_fix_permissions(state)
    elif args.suggest_env:
        cmd_suggest_env()
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
