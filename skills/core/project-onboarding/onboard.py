#!/usr/bin/env python3
"""
Project Onboarding scanner for OpenClaw.

Crawls a project directory to infer tech stack, build commands,
test conventions, and key structural patterns.

Usage:
    python3 onboard.py --scan /path/to/project        # Scan and print JSON summary
    python3 onboard.py --scan . --format markdown     # Print as PROJECT.md template
    python3 onboard.py --register /path/to/project    # Register in state after onboarding
    python3 onboard.py --list                          # List registered projects
    python3 onboard.py --refresh /path/to/project     # Re-scan and update state
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "project-onboarding" / "state.yaml"

# ── Detection rules ───────────────────────────────────────────────────────────

STACK_INDICATORS: list[tuple[str, str]] = [
    ("package.json",         "Node.js"),
    ("tsconfig.json",        "TypeScript"),
    ("pyproject.toml",       "Python"),
    ("setup.py",             "Python"),
    ("requirements.txt",     "Python"),
    ("Cargo.toml",           "Rust"),
    ("go.mod",               "Go"),
    ("pom.xml",              "Java/Maven"),
    ("build.gradle",         "Java/Gradle"),
    ("*.gemspec",            "Ruby"),
    ("Gemfile",              "Ruby"),
    ("composer.json",        "PHP"),
    ("*.csproj",             "C#/.NET"),
    ("mix.exs",              "Elixir"),
    ("pubspec.yaml",         "Dart/Flutter"),
]

BUILD_FILES = ["Makefile", "justfile", "taskfile.yml", "Taskfile.yml",
               "scripts/build.sh", "scripts/test.sh"]

TEST_PATTERNS = [
    ("__tests__/",      "Jest"),
    ("spec/",           "RSpec/Jasmine"),
    ("tests/",          "pytest/unittest"),
    ("test/",           "Go test / general"),
    ("*.test.ts",       "Jest"),
    ("*.spec.ts",       "Jasmine"),
    ("*_test.go",       "Go test"),
    ("test_*.py",       "pytest"),
]

CI_FILES = [
    ".github/workflows/",
    ".circleci/config.yml",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".travis.yml",
]


def detect_stack(root: Path) -> list[str]:
    stack = []
    for indicator, label in STACK_INDICATORS:
        if "*" in indicator:
            if list(root.glob(indicator)):
                stack.append(label)
        elif (root / indicator).exists():
            stack.append(label)
    return list(dict.fromkeys(stack))  # deduplicate, preserve order


def detect_build_commands(root: Path) -> list[str]:
    commands = []
    for f in BUILD_FILES:
        p = root / f
        if p.exists():
            commands.append(f"See {f}")
    # package.json scripts
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            scripts = data.get("scripts", {})
            for name in ["build", "test", "dev", "start", "lint"]:
                if name in scripts:
                    commands.append(f"npm run {name}")
        except (json.JSONDecodeError, Exception):
            pass
    # Makefile targets
    mk = root / "Makefile"
    if mk.exists():
        import re
        targets = re.findall(r"^([a-zA-Z][a-zA-Z0-9_-]*):", mk.read_text(), re.MULTILINE)
        commands.extend([f"make {t}" for t in targets[:8]])
    return commands[:10]


def detect_test_framework(root: Path) -> list[str]:
    found = []
    for pattern, label in TEST_PATTERNS:
        if pattern.endswith("/"):
            if (root / pattern.rstrip("/")).is_dir():
                found.append(label)
        elif "*" in pattern:
            if list(root.rglob(pattern)):
                found.append(label)
    return list(dict.fromkeys(found))


def detect_structure(root: Path) -> list[str]:
    important = ["src", "lib", "app", "internal", "pkg", "cmd",
                 "api", "web", "frontend", "backend", "services",
                 "components", "models", "controllers", "routes"]
    found = []
    for d in important:
        if (root / d).is_dir():
            found.append(d)
    return found


def detect_ci(root: Path) -> list[str]:
    found = []
    for f in CI_FILES:
        p = root / f
        if p.exists() or p.is_dir():
            found.append(f)
    return found


def scan_project(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    return {
        "path": str(root),
        "slug": root.name,
        "stack": detect_stack(root),
        "build_commands": detect_build_commands(root),
        "test_frameworks": detect_test_framework(root),
        "structure": detect_structure(root),
        "ci": detect_ci(root),
        "has_contributing": (root / "CONTRIBUTING.md").exists(),
        "has_readme": (root / "README.md").exists(),
        "scanned_at": datetime.now().isoformat(),
    }


def to_markdown(scan: dict) -> str:
    lines = [
        f"# Project: {scan['slug']}",
        f"",
        f"<!-- Generated by project-onboarding on {scan['scanned_at'][:10]} -->",
        f"<!-- Validate and extend this file — it is your agent's context for this project -->",
        f"",
        f"## Stack",
        f"{', '.join(scan['stack']) or '(not detected — add manually)'}",
        f"",
        f"## Build & Test Commands",
    ]
    for cmd in scan["build_commands"]:
        lines.append(f"- `{cmd}`")
    if scan["test_frameworks"]:
        lines.append(f"- Test framework: {', '.join(scan['test_frameworks'])}")
    lines += [
        f"",
        f"## Project Structure",
    ]
    for d in scan["structure"]:
        lines.append(f"- `{d}/`")
    lines += [
        f"",
        f"## Key Conventions",
        f"<!-- Fill in: naming conventions, file structure rules, API patterns -->",
        f"- (infer from CONTRIBUTING.md and existing code)",
        f"",
        f"## Things the Agent Must Never Do Here",
        f"<!-- Fill in: rules specific to this project -->",
        f"- Never commit to main directly",
        f"- Never delete migration files",
        f"",
        f"## Known Gotchas",
        f"<!-- Fill in: sharp edges discovered over time -->",
        f"- (add as you discover them)",
    ]
    return "\n".join(lines)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"projects": []}
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


def main():
    parser = argparse.ArgumentParser(description="Project onboarding scanner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", metavar="PATH")
    group.add_argument("--register", metavar="PATH")
    group.add_argument("--list", action="store_true")
    group.add_argument("--refresh", metavar="PATH")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    if args.list:
        state = load_state()
        projects = state.get("projects") or []
        if not projects:
            print("No projects registered.")
            return
        print(f"\nRegistered Projects ({len(projects)}):")
        for p in projects:
            v = "✓" if p.get("validated") else "?"
            print(f"  {v} {p['slug']}  —  {p['path']}")
            print(f"       Stack: {', '.join(p.get('stack', []))}")
        return

    path = args.scan or args.register or args.refresh
    root = Path(path)
    scan = scan_project(root)

    if args.scan:
        if args.format == "markdown":
            print(to_markdown(scan))
        else:
            print(json.dumps(scan, indent=2))
        return

    # register or refresh
    state = load_state()
    projects = state.get("projects") or []
    existing = next((p for p in projects if p["path"] == str(root.resolve())), None)

    now = datetime.now().isoformat()
    entry = {
        "slug": scan["slug"],
        "path": str(root.resolve()),
        "project_md": str(root.resolve() / "PROJECT.md"),
        "stack": scan["stack"],
        "onboarded_at": existing.get("onboarded_at", now) if existing else now,
        "last_refreshed": now,
        "validated": existing.get("validated", False) if existing else False,
    }

    if existing:
        projects = [p for p in projects if p["path"] != entry["path"]]
        print(f"✓ Refreshed: {entry['slug']}")
    else:
        print(f"✓ Registered: {entry['slug']}")

    projects.append(entry)
    state["projects"] = projects
    save_state(state)

    # Write PROJECT.md
    project_md_path = root.resolve() / "PROJECT.md"
    if not project_md_path.exists():
        project_md_path.write_text(to_markdown(scan))
        print(f"  PROJECT.md written to: {project_md_path}")
    else:
        print(f"  PROJECT.md already exists — review and update manually")


if __name__ == "__main__":
    main()
