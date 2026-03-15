#!/usr/bin/env python3
"""
Channel Context Bridge for OpenClaw.

Writes resumé cards at session end and checks for them at session start.
Enables seamless context continuity when switching between channels.

Usage:
    python3 bridge.py --write --topic "Refactoring auth" --decisions "Use JWT" --next "Write tests"
    python3 bridge.py --check          # Check for recent card (use at session start)
    python3 bridge.py --resume         # Print latest card in full
    python3 bridge.py --history        # Show last 7 cards
    python3 bridge.py --channel NAME   # Specify source channel (default: unknown)
"""

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "channel-context-bridge" / "state.yaml"
BRIDGE_DIR = OPENCLAW_DIR / "workspace" / "session-bridge"
MAX_HISTORY = 7


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"card_history": [], "auto_inject_hours": 24}
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


def card_to_markdown(card: dict) -> str:
    written = card.get("written_at", "")[:19]
    channel = card.get("source_channel", "unknown")
    lines = [
        f"# Session Resumé Card",
        f"*Written: {written} on {channel}*",
        f"",
        f"## What we were doing",
        card.get("topic", "(not specified)"),
        f"",
    ]
    decisions = card.get("decisions") or []
    if decisions:
        lines.append("## Key decisions made")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    questions = card.get("open_questions") or []
    if questions:
        lines.append("## Open questions")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    next_actions = card.get("next_actions") or []
    if next_actions:
        lines.append("## Next actions")
        for a in next_actions:
            lines.append(f"- {a}")
        lines.append("")

    context = card.get("critical_context", "")
    if context:
        lines.append("## Critical context")
        lines.append(context)
        lines.append("")

    return "\n".join(lines)


def primer_sentence(card: dict) -> str:
    """One-sentence primer for context injection."""
    written = card.get("written_at", "")[:16]
    channel = card.get("source_channel", "another channel")
    topic = card.get("topic", "a previous conversation")
    next_actions = card.get("next_actions") or []
    next_str = f" Next: {next_actions[0]}." if next_actions else ""
    return (f"Picking up from {channel} at {written}: {topic}.{next_str} "
            f"Say 'resume' for full context, or continue naturally.")


def cmd_write(state: dict, topic: str, decisions: list, questions: list,
              next_actions: list, context: str, channel: str) -> dict:
    now = datetime.now().isoformat()
    card = {
        "topic": topic,
        "decisions": decisions,
        "open_questions": questions,
        "next_actions": next_actions,
        "critical_context": context,
        "source_channel": channel,
        "written_at": now,
    }
    state["latest_card"] = card

    history = state.get("card_history") or []
    history.insert(0, card)
    state["card_history"] = history[:MAX_HISTORY]

    # Write to filesystem for easy access
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    (BRIDGE_DIR / "latest.md").write_text(card_to_markdown(card))
    for i, old_card in enumerate(history[1:], start=1):
        (BRIDGE_DIR / f"prev-{i}.md").write_text(card_to_markdown(old_card))

    print(f"✓ Resumé card written ({channel}): {topic[:60]}")
    print(f"  Location: {BRIDGE_DIR / 'latest.md'}")
    return state


def cmd_check(state: dict) -> None:
    card = state.get("latest_card")
    if not card:
        print("no-card")
        return

    auto_hours = int(state.get("auto_inject_hours") or 24)
    written_raw = card.get("written_at", "")
    try:
        written = datetime.fromisoformat(written_raw)
        age = datetime.now() - written
        if age < timedelta(hours=auto_hours):
            print(f"recent: {primer_sentence(card)}")
        else:
            print(f"stale ({age.days}d ago): {card.get('topic', '')}")
    except ValueError:
        print("no-card")


def cmd_resume(state: dict) -> None:
    card = state.get("latest_card")
    if not card:
        print("No resumé card found.")
        return
    print(card_to_markdown(card))


def cmd_history(state: dict) -> None:
    history = state.get("card_history") or []
    if not history:
        print("No session cards recorded yet.")
        return
    print(f"\nSession Bridge History ({len(history)} cards)")
    print(f"{'─' * 40}")
    for i, card in enumerate(history):
        label = "latest" if i == 0 else f"prev-{i}"
        written = card.get("written_at", "")[:16]
        channel = card.get("source_channel", "?")
        topic = card.get("topic", "?")[:60]
        print(f"  [{label}]  {written}  ({channel})")
        print(f"           {topic}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Channel context bridge")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--resume", action="store_true")
    group.add_argument("--history", action="store_true")
    parser.add_argument("--topic", default="")
    parser.add_argument("--decisions", default="")
    parser.add_argument("--questions", default="")
    parser.add_argument("--next", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--channel", default="unknown")
    args = parser.parse_args()

    state = load_state()

    if args.check:
        cmd_check(state)
        return
    if args.resume:
        cmd_resume(state)
        return
    if args.history:
        cmd_history(state)
        return

    if args.write:
        decisions = [d.strip() for d in args.decisions.split(";") if d.strip()]
        questions = [q.strip() for q in args.questions.split(";") if q.strip()]
        next_actions = [n.strip() for n in args.next.split(";") if n.strip()]
        state = cmd_write(state, args.topic, decisions, questions,
                         next_actions, args.context, args.channel)

    save_state(state)


if __name__ == "__main__":
    main()
