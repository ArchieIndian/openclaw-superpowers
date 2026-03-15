#!/usr/bin/env python3
"""
Skill Portability Checker for openclaw-superpowers.

Validates companion script OS/binary dependencies and checks whether
they are present on the current machine.

Usage:
    python3 check.py --check
    python3 check.py --check --skill obsidian-sync
    python3 check.py --fix-hints <skill>
    python3 check.py --format json
"""

import argparse
import importlib
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]

# Known OS-specific binaries
MACOS_ONLY_BINARIES = {
    "osascript", "pbcopy", "pbpaste", "open", "launchctl", "caffeinate",
    "defaults", "plutil", "say", "afplay", "mdfind", "mdls",
}
LINUX_ONLY_BINARIES = {
    "systemctl", "journalctl", "apt", "apt-get", "dpkg", "yum", "dnf",
    "pacman", "snap", "xclip", "xdotool", "notify-send", "xdg-open",
}
BREW_BINARY = "brew"

# Stdlib modules (not exhaustive, covers common ones)
STDLIB_MODULES = {
    "os", "sys", "re", "json", "yaml", "pathlib", "datetime", "time",
    "collections", "itertools", "functools", "typing", "io", "math",
    "random", "hashlib", "hmac", "base64", "struct", "copy", "enum",
    "abc", "dataclasses", "contextlib", "threading", "subprocess",
    "shutil", "tempfile", "glob", "fnmatch", "stat", "socket", "http",
    "urllib", "email", "csv", "sqlite3", "logging", "unittest", "argparse",
    "configparser", "getpass", "platform", "importlib", "inspect",
    "traceback", "warnings", "weakref", "gc", "signal", "textwrap",
    "string", "difflib", "html", "xml", "pprint", "decimal", "fractions",
}

# Patterns for detecting binary calls in scripts
BINARY_CALL_RE = re.compile(
    r'(?:subprocess\.(?:run|Popen|call|check_output|check_call)\s*\(\s*[\[\(]?\s*["\'])([a-z_\-]+)',
    re.I
)
SHELL_CALL_RE = re.compile(r'(?:os\.system|os\.popen)\s*\(\s*["\']([a-z_\-]+)', re.I)
SHUTIL_WHICH_RE = re.compile(r'shutil\.which\s*\(\s*["\']([a-z_\-]+)', re.I)
IMPORT_RE = re.compile(r'^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)', re.M)
HARDCODED_PATH_RE = re.compile(
    r'["\'](?:/usr/local/|/opt/homebrew/|/home/[a-z]+/|C:\\\\)', re.I
)


def current_os() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


# ── Frontmatter ───────────────────────────────────────────────────────────────

def parse_frontmatter(skill_md: Path) -> dict:
    try:
        text = skill_md.read_text()
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        end = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end = i
                break
        if end is None:
            return {}
        fm_text = "\n".join(lines[1:end])
        if HAS_YAML:
            return yaml.safe_load(fm_text) or {}
        fields = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip().strip('"').strip("'")
        return fields
    except Exception:
        return {}


# ── Script analysis ───────────────────────────────────────────────────────────

def extract_binary_calls(text: str) -> set[str]:
    binaries = set()
    for pattern in (BINARY_CALL_RE, SHELL_CALL_RE, SHUTIL_WHICH_RE):
        for m in pattern.finditer(text):
            binaries.add(m.group(1).lower())
    return binaries


def extract_imports(text: str) -> set[str]:
    imports = set()
    for m in IMPORT_RE.finditer(text):
        mod = m.group(1).split(".")[0]
        if mod not in STDLIB_MODULES:
            imports.add(mod)
    return imports


def is_importable(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def binary_present(name: str) -> bool:
    return shutil.which(name) is not None


# ── Skill checker ─────────────────────────────────────────────────────────────

def check_skill(skill_dir: Path, os_name: str) -> list[dict]:
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []

    fm = parse_frontmatter(skill_md)
    os_filter = fm.get("os_filter") or []
    if isinstance(os_filter, str):
        os_filter = [os_filter]
    os_filter = [str(o).lower() for o in os_filter]

    issues = []

    def issue(level, check, file_path, detail, fix_hint):
        return {
            "skill_name": skill_name,
            "level": level,
            "check": check,
            "file": str(file_path),
            "detail": detail,
            "fix_hint": fix_hint,
        }

    # Scan companion scripts
    for script in skill_dir.iterdir():
        if not script.is_file():
            continue
        if script.suffix not in (".py", ".sh"):
            continue

        try:
            text = script.read_text(errors="replace")
        except Exception:
            continue

        # Binary call analysis
        binaries = extract_binary_calls(text)

        for binary in binaries:
            # macOS-only binary
            if binary in MACOS_ONLY_BINARIES:
                if os_filter and "macos" not in os_filter:
                    issues.append(issue(
                        "FAIL", "OS_SPECIFIC_CALL", script,
                        f"Calls `{binary}` (macOS-only) but os_filter excludes macOS",
                        f"Remove macOS calls or set `os_filter: [macos]` in frontmatter."
                    ))
                elif not os_filter:
                    issues.append(issue(
                        "WARN", "OS_SPECIFIC_CALL", script,
                        f"Calls `{binary}` (macOS-only) but no os_filter declared",
                        f"Add `os_filter: [macos]` to frontmatter."
                    ))
                if os_name != "macos" and binary not in os_filter:
                    if not binary_present(binary):
                        issues.append(issue(
                            "FAIL", "MISSING_BINARY", script,
                            f"`{binary}` not found on this system",
                            f"Install `{binary}` or add `os_filter: [macos]` to frontmatter."
                        ))

            # Linux-only binary
            elif binary in LINUX_ONLY_BINARIES:
                if os_filter and "linux" not in os_filter:
                    issues.append(issue(
                        "FAIL", "OS_SPECIFIC_CALL", script,
                        f"Calls `{binary}` (Linux-only) but os_filter excludes Linux",
                        "Remove Linux-specific calls or add `linux` to os_filter."
                    ))
                elif not os_filter:
                    issues.append(issue(
                        "WARN", "OS_SPECIFIC_CALL", script,
                        f"Calls `{binary}` (Linux-only) but no os_filter declared",
                        "Add `os_filter: [linux]` to frontmatter."
                    ))

            # brew special case
            elif binary == BREW_BINARY:
                issues.append(issue(
                    "WARN", "BREW_ONLY", script,
                    "Script calls `brew` (Homebrew/macOS-only)",
                    "Add `os_filter: [macos]` or use a cross-platform alternative."
                ))

            # General binary — check if present
            else:
                if not binary_present(binary) and binary not in (
                    "python3", "python", "bash", "sh", "openclaw"
                ):
                    issues.append(issue(
                        "WARN", "MISSING_BINARY", script,
                        f"`{binary}` not found on PATH",
                        f"Install `{binary}` or add a fallback when it's missing."
                    ))

        # Hardcoded paths
        if HARDCODED_PATH_RE.search(text):
            issues.append(issue(
                "WARN", "HARDCODED_PATH", script,
                "Script contains hardcoded absolute paths that may not exist on all systems",
                "Replace with `Path.home()` or environment-variable-based paths."
            ))

        # Python imports (only for .py files)
        if script.suffix == ".py":
            imports = extract_imports(text)
            for mod in imports:
                if not is_importable(mod):
                    issues.append(issue(
                        "WARN", "PYTHON_IMPORT", script,
                        f"imports `{mod}` which is not installed on this system",
                        f"Install with `pip install {mod}` or add try/except ImportError."
                    ))

    # os_filter correctness: if os_filter present, check it's valid values
    valid_os_values = {"macos", "linux", "windows"}
    for os_val in os_filter:
        if os_val not in valid_os_values:
            issues.append(issue(
                "WARN", "INVALID_OS_FILTER", skill_md,
                f"os_filter contains unknown value: `{os_val}`",
                f"Valid values: {sorted(valid_os_values)}"
            ))

    return issues


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(single_skill: str, fmt: str) -> None:
    os_name = current_os()
    all_issues = []
    skills_checked = 0

    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            if single_skill and skill_dir.name != single_skill:
                continue
            issues = check_skill(skill_dir, os_name)
            all_issues.extend(issues)
            skills_checked += 1

    fails = sum(1 for i in all_issues if i["level"] == "FAIL")
    warns = sum(1 for i in all_issues if i["level"] == "WARN")
    py_ver = f"Python {sys.version_info.major}.{sys.version_info.minor}"

    if fmt == "json":
        print(json.dumps({
            "os": os_name,
            "python_version": py_ver,
            "skills_checked": skills_checked,
            "fail_count": fails,
            "warn_count": warns,
            "issues": all_issues,
        }, indent=2))
    else:
        print(f"\nSkill Portability Report — {os_name} ({py_ver})")
        print("─" * 50)
        print(f"  {skills_checked} skills checked | {fails} FAIL | {warns} WARN")
        print()
        if not all_issues:
            print("  ✓ All skills portable on this system.")
        else:
            by_skill: dict = {}
            for iss in all_issues:
                by_skill.setdefault(iss["skill_name"], []).append(iss)
            for sname, issues in sorted(by_skill.items()):
                for iss in issues:
                    icon = "✗" if iss["level"] == "FAIL" else "⚠"
                    print(f"  {icon} {sname}: {iss['check']}")
                    print(f"     {iss['detail']}")
                    print(f"     Fix: {iss['fix_hint']}")
                    print()
        print()

    sys.exit(1 if fails > 0 else 0)


def cmd_fix_hints(skill_name: str) -> None:
    os_name = current_os()
    for skills_root in SKILLS_DIRS:
        skill_dir = skills_root / skill_name
        if skill_dir.exists():
            issues = check_skill(skill_dir, os_name)
            if not issues:
                print(f"✓ No portability issues found for '{skill_name}'.")
                return
            print(f"\nFix hints for: {skill_name}")
            print("─" * 40)
            for iss in issues:
                print(f"  [{iss['level']}] {iss['check']}")
                print(f"    {iss['detail']}")
                print(f"    → {iss['fix_hint']}")
                print()
            return
    print(f"Skill '{skill_name}' not found.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Portability Checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--fix-hints", metavar="SKILL")
    parser.add_argument("--skill", metavar="NAME", help="Check single skill only")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.fix_hints:
        cmd_fix_hints(args.fix_hints)
    elif args.check:
        cmd_check(single_skill=args.skill, fmt=args.format)


if __name__ == "__main__":
    main()
