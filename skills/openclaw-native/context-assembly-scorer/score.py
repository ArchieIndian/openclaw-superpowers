#!/usr/bin/env python3
"""
Context Assembly Scorer for openclaw-superpowers.

Scores how well the current context represents the full conversation.
Detects information blind spots, stale summaries, and coverage gaps.

Usage:
    python3 score.py --score
    python3 score.py --score --verbose
    python3 score.py --blind-spots
    python3 score.py --drift
    python3 score.py --status
    python3 score.py --format json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "context-assembly-scorer" / "state.yaml"
MEMORY_FILE = OPENCLAW_DIR / "workspace" / "MEMORY.md"
CONTEXT_FILE = OPENCLAW_DIR / "workspace" / "CONTEXT.md"
MAX_HISTORY = 20

# ── Patterns for entity/decision detection ───────────────────────────────────

ENTITY_PATTERNS = [
    re.compile(r'(?:/[\w./-]+\.[\w]+)'),                    # file paths
    re.compile(r'https?://[^\s)]+'),                         # URLs
    re.compile(r'(?:class|def|function|const)\s+(\w+)'),     # code definitions
    re.compile(r'(?:GET|POST|PUT|DELETE|PATCH)\s+/[\w/-]+'),  # API endpoints
    re.compile(r'`([^`]{3,40})`'),                           # inline code refs
]

DECISION_MARKERS = [
    "decided", "chose", "chosen", "prefer", "preference",
    "always", "never", "must", "should not", "agreed",
    "convention", "standard", "rule", "policy", "approach",
]

TASK_MARKERS = [
    "todo", "TODO", "FIXME", "HACK", "pending", "in progress",
    "blocked", "waiting", "next step", "follow up", "need to",
]


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"blind_spots": [], "score_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"blind_spots": [], "score_history": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── Extraction ───────────────────────────────────────────────────────────────

def extract_topics(text: str) -> Counter:
    """Extract topic keywords from text."""
    # Remove code blocks and URLs
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    # Tokenize
    words = re.findall(r'[a-z][a-z0-9_-]{2,}', cleaned.lower())
    # Filter stopwords
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "were", "been", "have", "has", "had", "will", "would", "could",
        "should", "not", "but", "its", "also", "can", "into", "when",
        "then", "than", "more", "some", "each", "all", "any", "our",
        "your", "their", "which", "about", "just", "like", "very",
    }
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
    return Counter(filtered)


def extract_entities(text: str) -> set:
    """Extract named entities from text."""
    entities = set()
    for pattern in ENTITY_PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            if isinstance(m, tuple):
                m = m[0]
            if len(m) > 2:
                entities.add(m.strip())
    return entities


def extract_decisions(text: str) -> list[str]:
    """Extract decision statements from text."""
    decisions = []
    for line in text.split("\n"):
        line_lower = line.lower()
        for marker in DECISION_MARKERS:
            if marker in line_lower:
                decisions.append(line.strip()[:120])
                break
    return decisions


def extract_tasks(text: str) -> list[str]:
    """Extract task/todo references from text."""
    tasks = []
    for line in text.split("\n"):
        line_lower = line.lower()
        for marker in TASK_MARKERS:
            if marker in line_lower:
                tasks.append(line.strip()[:120])
                break
    return tasks


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_topic_coverage(memory_topics: Counter, context_topics: Counter) -> float:
    """Score: what % of important memory topics appear in context."""
    if not memory_topics:
        return 100.0
    # Focus on top 50 topics by frequency
    top_topics = {t for t, _ in memory_topics.most_common(50)}
    if not top_topics:
        return 100.0
    covered = sum(1 for t in top_topics if context_topics.get(t, 0) > 0)
    return round(covered / len(top_topics) * 100, 1)


def score_recency_bias(memory_text: str, context_text: str) -> float:
    """Score: is context over-representing recent entries vs. older important ones."""
    memory_lines = memory_text.split("\n")
    total = len(memory_lines)
    if total < 10:
        return 100.0

    # Split memory into thirds: old, mid, recent
    third = total // 3
    old_topics = extract_topics("\n".join(memory_lines[:third]))
    mid_topics = extract_topics("\n".join(memory_lines[third:2*third]))
    recent_topics = extract_topics("\n".join(memory_lines[2*third:]))
    ctx_topics = extract_topics(context_text)

    # Score each third's representation
    old_covered = sum(1 for t in old_topics if ctx_topics.get(t, 0) > 0)
    mid_covered = sum(1 for t in mid_topics if ctx_topics.get(t, 0) > 0)
    recent_covered = sum(1 for t in recent_topics if ctx_topics.get(t, 0) > 0)

    old_pct = old_covered / max(len(old_topics), 1) * 100
    mid_pct = mid_covered / max(len(mid_topics), 1) * 100
    recent_pct = recent_covered / max(len(recent_topics), 1) * 100

    # Penalize if old coverage is much lower than recent
    if recent_pct > 0:
        balance = (old_pct + mid_pct) / (2 * recent_pct) * 100
        return round(min(100.0, balance), 1)
    return 100.0


def score_entity_continuity(memory_entities: set, context_entities: set) -> float:
    """Score: named entities in history that are missing from context."""
    if not memory_entities:
        return 100.0
    covered = len(memory_entities & context_entities)
    return round(covered / len(memory_entities) * 100, 1)


def score_decision_retention(memory_decisions: list, context_text: str) -> float:
    """Score: are decisions still accessible in context."""
    if not memory_decisions:
        return 100.0
    ctx_lower = context_text.lower()
    retained = sum(1 for d in memory_decisions
                   if any(word in ctx_lower for word in d.lower().split()[:5]))
    return round(retained / len(memory_decisions) * 100, 1)


def score_task_continuity(memory_tasks: list, context_text: str) -> float:
    """Score: are active tasks still visible in context."""
    if not memory_tasks:
        return 100.0
    ctx_lower = context_text.lower()
    retained = sum(1 for t in memory_tasks
                   if any(word in ctx_lower for word in t.lower().split()[:5]))
    return round(retained / len(memory_tasks) * 100, 1)


def compute_overall(tc, rb, ec, dr, tcont) -> float:
    """Weighted overall score."""
    weighted = tc * 2.0 + rb * 1.5 + ec * 2.0 + dr * 2.0 + tcont * 1.5
    total_weight = 2.0 + 1.5 + 2.0 + 2.0 + 1.5
    return round(weighted / total_weight, 1)


def get_grade(score: float) -> str:
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    return "F"


def find_blind_spots(memory_text: str, context_text: str) -> list[dict]:
    """Find specific items missing from context."""
    spots = []
    mem_entities = extract_entities(memory_text)
    ctx_entities = extract_entities(context_text)
    missing_entities = mem_entities - ctx_entities

    for entity in sorted(missing_entities)[:20]:
        importance = "high" if "/" in entity or "http" in entity else "medium"
        spots.append({
            "type": "entity",
            "name": entity[:80],
            "importance": importance,
            "last_seen": "in full memory",
        })

    mem_decisions = extract_decisions(memory_text)
    ctx_lower = context_text.lower()
    for d in mem_decisions[:10]:
        if not any(word in ctx_lower for word in d.lower().split()[:5]):
            spots.append({
                "type": "decision",
                "name": d[:80],
                "importance": "critical",
                "last_seen": "in full memory",
            })

    mem_tasks = extract_tasks(memory_text)
    for t in mem_tasks[:10]:
        if not any(word in ctx_lower for word in t.lower().split()[:5]):
            spots.append({
                "type": "task",
                "name": t[:80],
                "importance": "high",
                "last_seen": "in full memory",
            })

    # Sort by importance
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    spots.sort(key=lambda s: order.get(s["importance"], 3))
    return spots


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_score(state: dict, verbose: bool, fmt: str) -> None:
    memory_text = MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""
    context_text = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else memory_text

    if not memory_text:
        print("No MEMORY.md found — nothing to score.")
        return

    mem_topics = extract_topics(memory_text)
    ctx_topics = extract_topics(context_text)
    mem_entities = extract_entities(memory_text)
    ctx_entities = extract_entities(context_text)
    mem_decisions = extract_decisions(memory_text)
    mem_tasks = extract_tasks(memory_text)

    tc = score_topic_coverage(mem_topics, ctx_topics)
    rb = score_recency_bias(memory_text, context_text)
    ec = score_entity_continuity(mem_entities, ctx_entities)
    dr = score_decision_retention(mem_decisions, context_text)
    tcont = score_task_continuity(mem_tasks, context_text)
    overall = compute_overall(tc, rb, ec, dr, tcont)
    grade = get_grade(overall)
    now = datetime.now().isoformat()

    score_data = {
        "overall": overall,
        "grade": grade,
        "topic_coverage": tc,
        "recency_bias": rb,
        "entity_continuity": ec,
        "decision_retention": dr,
        "task_continuity": tcont,
    }
    state["current_score"] = score_data
    state["last_score_at"] = now

    history = state.get("score_history") or []
    blind_spots = find_blind_spots(memory_text, context_text)
    history.insert(0, {
        "scored_at": now, "overall": overall,
        "grade": grade, "blind_spot_count": len(blind_spots),
    })
    state["score_history"] = history[:MAX_HISTORY]
    state["blind_spots"] = blind_spots
    save_state(state)

    if fmt == "json":
        print(json.dumps(score_data, indent=2))
    else:
        print(f"\nContext Assembly Score — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 55)
        print(f"  Overall:              {overall:>5}%  Grade: {grade}")
        if verbose:
            print(f"  Topic coverage:       {tc:>5}%  (2x weight)")
            print(f"  Recency bias:         {rb:>5}%  (1.5x weight)")
            print(f"  Entity continuity:    {ec:>5}%  (2x weight)")
            print(f"  Decision retention:   {dr:>5}%  (2x weight)")
            print(f"  Task continuity:      {tcont:>5}%  (1.5x weight)")
            print(f"\n  Memory stats:")
            print(f"    Topics: {len(mem_topics)} unique | Entities: {len(mem_entities)}")
            print(f"    Decisions: {len(mem_decisions)} | Tasks: {len(mem_tasks)}")
        print(f"  Blind spots: {len(blind_spots)}")
        print()


def cmd_blind_spots(state: dict, fmt: str) -> None:
    memory_text = MEMORY_FILE.read_text() if MEMORY_FILE.exists() else ""
    context_text = CONTEXT_FILE.read_text() if CONTEXT_FILE.exists() else memory_text
    spots = find_blind_spots(memory_text, context_text)

    if fmt == "json":
        print(json.dumps({"blind_spots": spots, "count": len(spots)}, indent=2))
    else:
        print(f"\nBlind Spots — {len(spots)} items missing from context")
        print("-" * 55)
        icons = {"critical": "!!", "high": "!", "medium": "~", "low": "."}
        for s in spots[:25]:
            icon = icons.get(s["importance"], "?")
            print(f"  {icon} [{s['importance'].upper():>8}] {s['type']:>8}: {s['name']}")
        print()


def cmd_drift(state: dict, fmt: str) -> None:
    history = state.get("score_history") or []
    if fmt == "json":
        print(json.dumps({"score_history": history}, indent=2))
    else:
        print(f"\nCoverage Drift — {len(history)} data points")
        print("-" * 55)
        if not history:
            print("  No score history yet.")
        else:
            for h in history[:15]:
                ts = h.get("scored_at", "?")[:16]
                overall = h.get("overall", 0)
                grade = h.get("grade", "?")
                spots = h.get("blind_spot_count", 0)
                bar = "=" * int(overall / 10) + "-" * (10 - int(overall / 10))
                print(f"  {ts}  [{bar}] {overall}% ({grade})  {spots} blind spots")
        # Trend
        if len(history) >= 2:
            latest = history[0].get("overall", 0)
            prev = history[1].get("overall", 0)
            delta = latest - prev
            trend = "improving" if delta > 0 else "declining" if delta < 0 else "stable"
            print(f"\n  Trend: {trend} ({'+' if delta>0 else ''}{delta}%)")
        print()


def cmd_status(state: dict) -> None:
    last = state.get("last_score_at", "never")
    score = state.get("current_score") or {}
    print(f"\nContext Assembly Scorer — Last score: {last}")
    if score:
        print(f"  Overall: {score.get('overall', 0)}% ({score.get('grade', '?')})")
    spots = state.get("blind_spots") or []
    print(f"  Blind spots: {len(spots)}")
    critical = sum(1 for s in spots if s.get("importance") == "critical")
    if critical:
        print(f"  Critical blind spots: {critical}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Context Assembly Scorer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--score", action="store_true", help="Score current context assembly")
    group.add_argument("--blind-spots", action="store_true", help="List topics missing from context")
    group.add_argument("--drift", action="store_true", help="Compare scores over time")
    group.add_argument("--status", action="store_true", help="Last score summary")
    parser.add_argument("--verbose", action="store_true", help="Detailed per-dimension breakdown")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.score:
        cmd_score(state, args.verbose, args.format)
    elif args.blind_spots:
        cmd_blind_spots(state, args.format)
    elif args.drift:
        cmd_drift(state, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
