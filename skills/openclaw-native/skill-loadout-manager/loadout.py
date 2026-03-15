#!/usr/bin/env python3
"""
Skill Loadout Manager for openclaw-superpowers.

Manages named skill profiles to control which skills are active,
preventing system prompt bloat from too many installed skills.

Usage:
    python3 loadout.py --list
    python3 loadout.py --create <name>
    python3 loadout.py --add <loadout> <skill> [<skill> ...]
    python3 loadout.py --remove <loadout> <skill>
    python3 loadout.py --activate <name>
    python3 loadout.py --activate --all
    python3 loadout.py --show <name>
    python3 loadout.py --status
    python3 loadout.py --pin <skill>
    python3 loadout.py --estimate [<name>|--all]
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "skill-loadout-manager" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]
MAX_HISTORY = 20

# Skills that should always be active (security + recovery)
DEFAULT_PINNED = [
    "dangerous-action-guard",
    "prompt-injection-guard",
    "agent-self-recovery",
    "task-handoff",
]

# Pre-built loadout seeds
PRESET_LOADOUTS = {
    "minimal": {
        "description": "Safety and recovery essentials only",
        "skills": [
            "dangerous-action-guard",
            "prompt-injection-guard",
            "agent-self-recovery",
            "task-handoff",
            "context-window-management",
        ],
    },
    "coding": {
        "description": "Software development workflow",
        "skills": [
            "systematic-debugging",
            "test-driven-development",
            "verification-before-completion",
            "subagent-driven-development",
            "skill-doctor",
            "dangerous-action-guard",
        ],
    },
    "research": {
        "description": "Research and knowledge synthesis",
        "skills": [
            "fact-check-before-trust",
            "brainstorming",
            "writing-plans",
            "channel-context-bridge",
            "persistent-memory-hygiene",
        ],
    },
    "ops": {
        "description": "Operations, monitoring, and cost management",
        "skills": [
            "cron-hygiene",
            "spend-circuit-breaker",
            "loop-circuit-breaker",
            "workspace-integrity-guardian",
            "secrets-hygiene",
            "installed-skill-auditor",
        ],
    },
}


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "active_loadout": "all",
            "pinned_skills": list(DEFAULT_PINNED),
            "loadouts": {},
            "switch_history": [],
        }
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


# ── Skill discovery ───────────────────────────────────────────────────────────

def all_installed_skills() -> list[str]:
    names = []
    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for d in sorted(skills_root.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                names.append(d.name)
    return names


def skill_description_tokens(skill_name: str) -> int:
    """Rough estimate of tokens contributed by this skill's description."""
    for skills_root in SKILLS_DIRS:
        skill_md = skills_root / skill_name / "SKILL.md"
        if skill_md.exists():
            try:
                text = skill_md.read_text()
                # Extract description from frontmatter
                lines = text.splitlines()
                for line in lines[1:20]:
                    if line.strip() == "---":
                        break
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                        return max(1, len(desc.split()) * 4 // 3)
            except Exception:
                pass
    return 20  # default estimate


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(state: dict) -> None:
    active = state.get("active_loadout", "all")
    loadouts = state.get("loadouts") or {}
    print(f"\nSkill Loadouts  (active: {active})")
    print("─" * 40)
    print(f"  {'all':20s}  (all installed skills)")
    for name, ldef in sorted(loadouts.items()):
        marker = "▶" if name == active else " "
        skill_count = len(ldef.get("skills") or [])
        desc = ldef.get("description", "")[:40]
        print(f"  {marker} {name:20s}  {skill_count:2d} skills  {desc}")
    print()


def cmd_create(state: dict, name: str, description: str = "") -> None:
    loadouts = state.get("loadouts") or {}
    if name in loadouts:
        print(f"Loadout '{name}' already exists. Use --add to add skills.")
        return
    preset = PRESET_LOADOUTS.get(name, {})
    loadouts[name] = {
        "name": name,
        "skills": list(preset.get("skills", [])),
        "description": description or preset.get("description", ""),
        "created_at": datetime.now().isoformat(),
        "last_used": None,
    }
    state["loadouts"] = loadouts
    save_state(state)
    seed_count = len(loadouts[name]["skills"])
    seed_msg = f" (seeded with {seed_count} preset skills)" if seed_count else ""
    print(f"✓ Created loadout '{name}'{seed_msg}.")


def cmd_add(state: dict, loadout_name: str, skills: list[str]) -> None:
    loadouts = state.get("loadouts") or {}
    if loadout_name not in loadouts:
        print(f"Loadout '{loadout_name}' not found. Run --create {loadout_name} first.")
        return
    existing = set(loadouts[loadout_name].get("skills") or [])
    added = []
    for skill in skills:
        if skill not in existing:
            existing.add(skill)
            added.append(skill)
    loadouts[loadout_name]["skills"] = sorted(existing)
    state["loadouts"] = loadouts
    save_state(state)
    if added:
        print(f"✓ Added to '{loadout_name}': {', '.join(added)}")
    else:
        print(f"All skills already in '{loadout_name}'.")


def cmd_remove(state: dict, loadout_name: str, skill: str) -> None:
    loadouts = state.get("loadouts") or {}
    if loadout_name not in loadouts:
        print(f"Loadout '{loadout_name}' not found.")
        return
    skills = loadouts[loadout_name].get("skills") or []
    if skill in skills:
        skills.remove(skill)
        loadouts[loadout_name]["skills"] = skills
        state["loadouts"] = loadouts
        save_state(state)
        print(f"✓ Removed '{skill}' from '{loadout_name}'.")
    else:
        print(f"'{skill}' not in loadout '{loadout_name}'.")


def cmd_activate(state: dict, name: str) -> None:
    loadouts = state.get("loadouts") or {}
    if name != "all" and name not in loadouts:
        print(f"Loadout '{name}' not found. Create it first with --create {name}.")
        return

    previous = state.get("active_loadout", "all")
    state["active_loadout"] = name

    if name != "all":
        loadouts[name]["last_used"] = datetime.now().isoformat()
        state["loadouts"] = loadouts

    history = state.get("switch_history") or []
    skill_count = (len(loadouts.get(name, {}).get("skills") or [])
                   if name != "all" else len(all_installed_skills()))
    history.insert(0, {
        "switched_at": datetime.now().isoformat(),
        "from_loadout": previous,
        "to_loadout": name,
        "skill_count": skill_count,
    })
    state["switch_history"] = history[:MAX_HISTORY]
    save_state(state)
    print(f"✓ Activated loadout '{name}' ({skill_count} skills).")
    print(f"  Takes effect on next OpenClaw session start.")


def cmd_show(state: dict, name: str) -> None:
    loadouts = state.get("loadouts") or {}
    pinned = set(state.get("pinned_skills") or [])

    if name == "all":
        skills = all_installed_skills()
        print(f"\nLoadout: all ({len(skills)} skills)")
    elif name in loadouts:
        ldef = loadouts[name]
        skills = sorted(ldef.get("skills") or [])
        print(f"\nLoadout: {name} ({len(skills)} skills)")
        if ldef.get("description"):
            print(f"  {ldef['description']}")
    else:
        print(f"Loadout '{name}' not found.")
        return

    print("─" * 40)
    for skill in skills:
        pin_marker = " [pinned]" if skill in pinned else ""
        print(f"  - {skill}{pin_marker}")
    print()


def cmd_pin(state: dict, skill: str) -> None:
    pinned = set(state.get("pinned_skills") or [])
    pinned.add(skill)
    state["pinned_skills"] = sorted(pinned)
    save_state(state)
    print(f"✓ Pinned '{skill}' — will be included in all loadouts.")


def cmd_estimate(state: dict, name: str) -> None:
    if name == "all":
        skills = all_installed_skills()
    else:
        loadouts = state.get("loadouts") or {}
        if name not in loadouts:
            print(f"Loadout '{name}' not found.")
            return
        skills = loadouts[name].get("skills") or []

    total_tokens = sum(skill_description_tokens(s) for s in skills)
    all_skills = all_installed_skills()
    all_tokens = sum(skill_description_tokens(s) for s in all_skills)
    savings = all_tokens - total_tokens

    print(f"\nToken estimate for loadout '{name}'")
    print("─" * 40)
    print(f"  Skills in loadout : {len(skills)}")
    print(f"  Est. tokens       : ~{total_tokens}")
    if name != "all":
        print(f"  All skills total  : ~{all_tokens}")
        pct = int(100 * savings / all_tokens) if all_tokens else 0
        print(f"  Token savings     : ~{savings} ({pct}% reduction)")
    print()


def cmd_status(state: dict) -> None:
    active = state.get("active_loadout", "all")
    pinned = state.get("pinned_skills") or []
    history = state.get("switch_history") or []
    print(f"\nActive loadout: {active}")
    if pinned:
        print(f"Pinned skills : {', '.join(pinned)}")
    if history:
        last = history[0]
        print(f"Last switch   : {last.get('switched_at','')[:16]} "
              f"({last.get('from_loadout','')} → {last.get('to_loadout','')})")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Loadout Manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--create", metavar="NAME")
    group.add_argument("--add", nargs="+", metavar="ARG",
                       help="<loadout> <skill> [<skill> ...]")
    group.add_argument("--remove", nargs=2, metavar=("LOADOUT", "SKILL"))
    group.add_argument("--activate", metavar="NAME")
    group.add_argument("--show", metavar="NAME")
    group.add_argument("--pin", metavar="SKILL")
    group.add_argument("--estimate", metavar="NAME")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--all", action="store_true",
                        help="With --activate or --estimate: use all skills")
    parser.add_argument("--description", metavar="TEXT", default="",
                        help="With --create: loadout description")
    args = parser.parse_args()

    state = load_state()

    if args.list:
        cmd_list(state)
    elif args.create:
        cmd_create(state, args.create, args.description)
    elif args.add:
        if len(args.add) < 2:
            print("Usage: --add <loadout> <skill> [<skill> ...]")
            sys.exit(1)
        cmd_add(state, args.add[0], args.add[1:])
    elif args.remove:
        cmd_remove(state, args.remove[0], args.remove[1])
    elif args.activate:
        cmd_activate(state, "all" if args.all else args.activate)
    elif args.show:
        cmd_show(state, "all" if args.all else args.show)
    elif args.pin:
        cmd_pin(state, args.pin)
    elif args.estimate:
        cmd_estimate(state, "all" if args.all else args.estimate)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
