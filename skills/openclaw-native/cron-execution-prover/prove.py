#!/usr/bin/env python3
from __future__ import annotations

"""
Cron Execution Prover for openclaw-superpowers.

Maintains a proof ledger around cron-driven workflows so start/finish/failure
and evidence are explicit.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "cron-execution-prover" / "state.yaml"
MAX_RUNS = 100
MAX_HISTORY = 12
STALE_AFTER_MINUTES = 60


def default_state() -> dict:
    return {
        "runs": [],
        "stale_runs": [],
        "last_report_at": "",
        "report_history": [],
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


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def find_run(state: dict, skill: str, run_id: str) -> dict | None:
    for item in state.get("runs", []):
        if item.get("skill") == skill and item.get("run_id") == run_id:
            return item
    return None


def ensure_run(state: dict, skill: str, run_id: str) -> dict:
    existing = find_run(state, skill, run_id)
    if existing:
        return existing
    entry = {
        "skill": skill,
        "run_id": run_id,
        "expected_at": "",
        "started_at": "",
        "finished_at": "",
        "status": "expected",
        "evidence": [],
        "notes": "",
    }
    state["runs"] = [entry] + (state.get("runs") or [])
    state["runs"] = state["runs"][:MAX_RUNS]
    return entry


def refresh_stale(state: dict) -> None:
    stale = []
    current = datetime.now()
    for item in state.get("runs", []):
        if item.get("status") in {"succeeded", "failed"}:
            continue
        ts = item.get("started_at") or item.get("expected_at")
        if not ts:
            continue
        try:
            age = int((current - datetime.fromisoformat(ts)).total_seconds() / 60)
        except ValueError:
            continue
        if age > STALE_AFTER_MINUTES:
            item["status"] = "stale"
            stale.append(
                {
                    "skill": item.get("skill", ""),
                    "run_id": item.get("run_id", ""),
                    "expected_at": item.get("expected_at", ""),
                    "age_minutes": age,
                }
            )
    state["stale_runs"] = stale


def record_history(state: dict) -> None:
    refresh_stale(state)
    now = now_iso()
    history = state.get("report_history") or []
    history.insert(
        0,
        {
            "reported_at": now,
            "total_runs": len(state.get("runs", [])),
            "stale_run_count": len(state.get("stale_runs", [])),
            "failed_run_count": sum(1 for item in state.get("runs", []) if item.get("status") == "failed"),
        },
    )
    state["last_report_at"] = now
    state["report_history"] = history[:MAX_HISTORY]


def print_report(state: dict, stale_only: bool = False) -> None:
    refresh_stale(state)
    runs = state.get("runs", [])
    stale_runs = state.get("stale_runs", [])
    failed_count = sum(1 for item in runs if item.get("status") == "failed")
    print("\nCron Execution Prover")
    print("───────────────────────────────────────────────────────")
    print(f"  {len(runs)} tracked runs | {len(stale_runs)} stale | {failed_count} failed")
    if stale_only:
        if not stale_runs:
            print("\n  No stale runs.")
            return
        print()
        for item in stale_runs:
            print(f"  STALE {item['skill']} ({item['run_id']})")
        return
    if not runs:
        print("\n  No runs recorded.")
        return
    print()
    for item in runs[:10]:
        print(f"  {item.get('status', '').upper():10} {item.get('skill', '')} ({item.get('run_id', '')})")
        if item.get("notes"):
            print(f"             {item['notes']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Proof ledger for cron-driven workflows")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--expect", metavar="SKILL", help="Record an expected run")
    group.add_argument("--start", metavar="SKILL", help="Mark a run started")
    group.add_argument("--finish", metavar="SKILL", help="Mark a run finished")
    group.add_argument("--fail", metavar="SKILL", help="Mark a run failed")
    group.add_argument("--stale", action="store_true", help="Show stale runs")
    group.add_argument("--report", action="store_true", help="Show run report")
    parser.add_argument("--run-id", help="Unique run identifier")
    parser.add_argument("--expected-at", help="Expected run time in ISO format")
    parser.add_argument("--evidence", nargs="*", default=[], help="Proof artifacts or side effects")
    parser.add_argument("--notes", default="", help="Extra notes")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    state = load_state()
    if args.expect:
        run_id = args.run_id or f"{args.expect}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        run = ensure_run(state, args.expect, run_id)
        run["expected_at"] = args.expected_at or now_iso()
        run["notes"] = args.notes or run.get("notes", "")
        save_state(state)
    elif args.start:
        if not args.run_id:
            raise SystemExit("--run-id is required for --start")
        run = ensure_run(state, args.start, args.run_id)
        run["started_at"] = now_iso()
        run["status"] = "in_progress"
        if args.notes:
            run["notes"] = args.notes
        save_state(state)
    elif args.finish:
        if not args.run_id:
            raise SystemExit("--run-id is required for --finish")
        run = ensure_run(state, args.finish, args.run_id)
        run["finished_at"] = now_iso()
        run["status"] = "succeeded"
        run["evidence"] = args.evidence or run.get("evidence", [])
        if args.notes:
            run["notes"] = args.notes
        save_state(state)
    elif args.fail:
        if not args.run_id:
            raise SystemExit("--run-id is required for --fail")
        run = ensure_run(state, args.fail, args.run_id)
        run["finished_at"] = now_iso()
        run["status"] = "failed"
        run["evidence"] = args.evidence or run.get("evidence", [])
        run["notes"] = args.notes or run.get("notes", "")
        save_state(state)

    if args.report or args.stale:
        record_history(state)
        save_state(state)

    refresh_stale(state)
    if args.format == "json":
        print(json.dumps(state, indent=2))
        return
    if args.stale:
        print_report(state, stale_only=True)
    else:
        print_report(state)


if __name__ == "__main__":
    main()
