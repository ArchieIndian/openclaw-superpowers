#!/usr/bin/env python3
"""
Compaction Resilience Guard for openclaw-superpowers.

Monitors memory compaction for failures and enforces a 3-level
fallback chain: normal → aggressive → deterministic truncation.

Usage:
    python3 guard.py --check
    python3 guard.py --check --file <summary.yaml>
    python3 guard.py --simulate <text>
    python3 guard.py --report
    python3 guard.py --status
    python3 guard.py --format json
"""

import argparse
import json
import math
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "compaction-resilience-guard" / "state.yaml"
DAG_STATE_FILE = OPENCLAW_DIR / "skill-state" / "memory-dag-compactor" / "state.yaml"
MAX_HISTORY = 20

# Thresholds
MIN_SUMMARY_LENGTH = 10
MAX_ENTROPY = 5.0
REPETITION_THRESHOLD = 3
REPETITION_MIN_LENGTH = 20


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"level_usage": {"l1_normal": 0, "l2_aggressive": 0, "l3_deterministic": 0},
                "failures": [], "check_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"level_usage": {"l1_normal": 0, "l2_aggressive": 0, "l3_deterministic": 0},
                "failures": [], "check_history": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


def load_dag_state() -> dict:
    if not DAG_STATE_FILE.exists():
        return {}
    try:
        text = DAG_STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def estimate_tokens(text: str) -> int:
    return len(text) // 4


# ── Failure detection ────────────────────────────────────────────────────────

def shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of character distribution."""
    if not text:
        return 0.0
    freq = Counter(text)
    total = len(text)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 2)


def detect_repetition(text: str) -> bool:
    """Detect if the same 20+ char phrase is repeated 3+ times."""
    if len(text) < REPETITION_MIN_LENGTH * REPETITION_THRESHOLD:
        return False
    # Sliding window of REPETITION_MIN_LENGTH chars
    phrases = Counter()
    for i in range(len(text) - REPETITION_MIN_LENGTH):
        phrase = text[i:i + REPETITION_MIN_LENGTH]
        phrases[phrase] += 1
    return any(count >= REPETITION_THRESHOLD for count in phrases.values())


def validate_summary(content: str, input_tokens: int = 0) -> dict:
    """Validate a single summary and return failure info if any."""
    failures = []

    # Check: empty
    if len(content.strip()) < MIN_SUMMARY_LENGTH:
        failures.append("empty")

    # Check: inflation (summary larger than input)
    output_tokens = estimate_tokens(content)
    if input_tokens > 0 and output_tokens > input_tokens:
        failures.append("inflation")

    # Check: garbled (high entropy = random characters)
    entropy = shannon_entropy(content)
    if entropy > MAX_ENTROPY:
        failures.append("garbled")

    # Check: repetition
    if detect_repetition(content):
        failures.append("repetition")

    # Check: fallback markers
    if "[FALLBACK]" in content or "[TRUNCATED]" in content:
        failures.append("truncation_marker")

    return {
        "valid": len(failures) == 0,
        "failures": failures,
        "output_tokens": output_tokens,
        "entropy": entropy,
    }


# ── Three-level fallback chain ───────────────────────────────────────────────

def l1_normal(text: str) -> str:
    """Level 1: Standard summarization — keep first 40% by lines."""
    lines = text.split("\n")
    keep = max(3, len(lines) * 40 // 100)
    summary = "\n".join(lines[:keep])
    return summary.strip()


def l2_aggressive(text: str) -> str:
    """Level 2: Aggressive — keep only lines with substance (no blanks, short lines)."""
    lines = text.split("\n")
    substantial = [l for l in lines if len(l.strip()) > 20]
    keep = max(3, len(substantial) * 30 // 100)
    summary = "\n".join(substantial[:keep])
    return summary.strip()


def l3_deterministic(text: str) -> str:
    """Level 3: Deterministic truncation — first 30% + last 20%, drop middle."""
    lines = text.split("\n")
    total = len(lines)
    if total <= 5:
        return text.strip()
    head_count = max(2, total * 30 // 100)
    tail_count = max(1, total * 20 // 100)
    head = lines[:head_count]
    tail = lines[-tail_count:]
    dropped = total - head_count - tail_count
    summary = "\n".join(head) + f"\n[... {dropped} lines truncated ...]\n" + "\n".join(tail)
    return summary.strip()


def run_fallback_chain(text: str) -> tuple[str, int]:
    """Run the 3-level fallback chain, return (result, level_used)."""
    input_tokens = estimate_tokens(text)

    # Level 1
    result = l1_normal(text)
    check = validate_summary(result, input_tokens)
    if check["valid"]:
        return result, 1

    # Level 2
    result = l2_aggressive(text)
    check = validate_summary(result, input_tokens)
    if check["valid"]:
        return result, 2

    # Level 3 — always succeeds
    result = l3_deterministic(text)
    return result, 3


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_check(state: dict, file_path: str | None, fmt: str) -> None:
    now = datetime.now().isoformat()
    failures_found = 0
    escalations = 0
    summaries_checked = 0

    if file_path:
        # Check a specific file
        path = Path(file_path)
        if not path.exists():
            print(f"Error: file '{file_path}' not found.")
            sys.exit(1)
        content = path.read_text()
        check = validate_summary(content)
        summaries_checked = 1
        if not check["valid"]:
            failures_found = 1
    else:
        # Check all DAG summaries
        dag = load_dag_state()
        nodes = dag.get("dag_nodes") or []
        results = []

        for node in nodes:
            content = node.get("content", "")
            check = validate_summary(content)
            summaries_checked += 1
            if not check["valid"]:
                failures_found += 1
                for f_type in check["failures"]:
                    failure_record = {
                        "summary_id": node.get("id", "unknown"),
                        "failure_type": f_type,
                        "level_used": 1,
                        "input_tokens": 0,
                        "output_tokens": check["output_tokens"],
                        "detected_at": now,
                    }
                    existing_failures = state.get("failures") or []
                    existing_failures.append(failure_record)
                    state["failures"] = existing_failures[-50:]  # Keep last 50
                    escalations += 1

                results.append({
                    "id": node.get("id"), "failures": check["failures"],
                    "entropy": check["entropy"], "tokens": check["output_tokens"],
                })

        if fmt != "json" and results:
            for r in results:
                print(f"  ! {r['id']}: {', '.join(r['failures'])} "
                      f"(entropy={r['entropy']}, {r['tokens']} tok)")

    state["last_check_at"] = now
    history = state.get("check_history") or []
    history.insert(0, {
        "checked_at": now, "summaries_checked": summaries_checked,
        "failures_found": failures_found, "escalations": escalations,
    })
    state["check_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps({"summaries_checked": summaries_checked,
                          "failures_found": failures_found,
                          "escalations": escalations}, indent=2))
    else:
        print(f"\nCompaction Resilience Check — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 50)
        print(f"  Summaries checked:  {summaries_checked}")
        print(f"  Failures found:     {failures_found}")
        print(f"  Escalations needed: {escalations}")
        status = "HEALTHY" if failures_found == 0 else "DEGRADED"
        print(f"  Status: {status}")
        print()


def cmd_simulate(state: dict, text: str, fmt: str) -> None:
    input_tokens = estimate_tokens(text)
    result, level = run_fallback_chain(text)
    output_tokens = estimate_tokens(result)

    # Update level usage
    usage = state.get("level_usage") or {"l1_normal": 0, "l2_aggressive": 0, "l3_deterministic": 0}
    level_key = {1: "l1_normal", 2: "l2_aggressive", 3: "l3_deterministic"}[level]
    usage[level_key] = usage.get(level_key, 0) + 1
    state["level_usage"] = usage
    save_state(state)

    if fmt == "json":
        print(json.dumps({"level_used": level, "input_tokens": input_tokens,
                          "output_tokens": output_tokens, "result": result[:500]}, indent=2))
    else:
        print(f"\nFallback Chain Simulation")
        print("-" * 50)
        print(f"  Input:  {input_tokens} tokens ({len(text)} chars)")
        print(f"  Level used: L{level} ({level_key})")
        print(f"  Output: {output_tokens} tokens")
        ratio = round(output_tokens / max(input_tokens, 1) * 100)
        print(f"  Compression: {ratio}%")
        print(f"\n  Result preview:")
        for line in result.split("\n")[:10]:
            print(f"    {line}")
        if result.count("\n") > 10:
            print(f"    ... ({result.count(chr(10))-10} more lines)")
        print()


def cmd_report(state: dict, fmt: str) -> None:
    usage = state.get("level_usage") or {}
    failures = state.get("failures") or []
    total = sum(usage.values())

    if fmt == "json":
        print(json.dumps({"level_usage": usage, "total_compactions": total,
                          "recent_failures": failures[-10:]}, indent=2))
    else:
        print(f"\nCompaction Resilience Report")
        print("-" * 50)
        print(f"  Total compactions tracked: {total}")
        if total > 0:
            l1 = usage.get("l1_normal", 0)
            l2 = usage.get("l2_aggressive", 0)
            l3 = usage.get("l3_deterministic", 0)
            print(f"  L1 Normal:        {l1:>5} ({l1/total*100:.0f}%)")
            print(f"  L2 Aggressive:    {l2:>5} ({l2/total*100:.0f}%)")
            print(f"  L3 Deterministic: {l3:>5} ({l3/total*100:.0f}%)")
            if l3 / total > 0.1:
                print(f"\n  WARNING: L3 usage > 10% — indicates systemic LLM issue")
        print(f"\n  Recent failures: {len(failures)}")
        for f in failures[-5:]:
            print(f"    {f.get('summary_id', '?')}: {f.get('failure_type', '?')} "
                  f"(L{f.get('level_used', '?')})")
        print()


def cmd_status(state: dict) -> None:
    last = state.get("last_check_at", "never")
    usage = state.get("level_usage") or {}
    total = sum(usage.values())
    l3 = usage.get("l3_deterministic", 0)
    print(f"\nCompaction Resilience Guard — Last check: {last}")
    print(f"  {total} compactions tracked | L3 fallbacks: {l3}")
    history = state.get("check_history") or []
    if history:
        h = history[0]
        print(f"  Last: {h.get('summaries_checked', 0)} checked, "
              f"{h.get('failures_found', 0)} failures")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compaction Resilience Guard")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Validate recent compaction outputs")
    group.add_argument("--simulate", type=str, metavar="TEXT", help="Run 3-level chain on sample text")
    group.add_argument("--report", action="store_true", help="Show failure/escalation history")
    group.add_argument("--status", action="store_true", help="Last check summary")
    parser.add_argument("--file", type=str, metavar="PATH", help="Check a specific summary file")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.check:
        cmd_check(state, args.file, args.format)
    elif args.simulate:
        cmd_simulate(state, args.simulate, args.format)
    elif args.report:
        cmd_report(state, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
