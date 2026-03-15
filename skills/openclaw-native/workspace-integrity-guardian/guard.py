#!/usr/bin/env python3
"""
Workspace Integrity Guardian for OpenClaw.

Hashes critical workspace files, detects drift, and prompts recovery.

Usage:
    python3 guard.py --baseline          # Record current state as trusted baseline
    python3 guard.py --check             # Compare current files to baseline (cron mode)
    python3 guard.py --restore PATH      # Restore a file from stored baseline
    python3 guard.py --accept PATH       # Accept current version as new baseline
    python3 guard.py --add-file PATH     # Add a file to monitoring list
    python3 guard.py --remove-file PATH  # Stop monitoring a file
    python3 guard.py --status            # Show monitored files + last check
"""

import argparse
import base64
import hashlib
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
WORKSPACE_DIR = OPENCLAW_DIR / "workspace"
STATE_FILE = OPENCLAW_DIR / "skill-state" / "workspace-integrity-guardian" / "state.yaml"

DEFAULT_MONITORED = [
    str(WORKSPACE_DIR / "SOUL.md"),
    str(WORKSPACE_DIR / "AGENTS.md"),
    str(WORKSPACE_DIR / "MEMORY.md"),
    str(WORKSPACE_DIR / "IDENTITY.md"),
]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"baseline": [], "monitored_paths": list(DEFAULT_MONITORED),
                "drift_history": [], "baseline_content": []}
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
    else:
        with open(STATE_FILE, "w") as f:
            for k, v in state.items():
                f.write(f"{k}: {v!r}\n")


def sha256_file(path: Path) -> tuple[str, int]:
    """Return (hex_digest, size_bytes) or ('MISSING', 0) if file absent."""
    if not path.exists():
        return "MISSING", 0
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def classify_change(old_size: int, new_size: int, old_hash: str, new_hash: str) -> str:
    if new_hash == "MISSING":
        return "deletion"
    if old_hash == "MISSING":
        return "append_only"
    if new_size > old_size * 0.9 and old_size > 0:
        return "append_only"
    if new_size < old_size * 0.7:
        return "truncation"
    return "full_replacement"


def cmd_baseline(state: dict) -> dict:
    paths = state.get("monitored_paths") or DEFAULT_MONITORED
    baseline = []
    content_store = []
    now = datetime.now().isoformat()

    for path_str in paths:
        p = Path(path_str).expanduser()
        digest, size = sha256_file(p)
        if digest == "MISSING":
            print(f"  SKIP (not found): {p}")
            continue
        baseline.append({
            "path": path_str,
            "sha256": digest,
            "size_bytes": size,
            "baselined_at": now,
        })
        content_store.append({
            "path": path_str,
            "content_b64": base64.b64encode(p.read_bytes()).decode(),
            "stored_at": now,
        })
        print(f"  ✓ Baselined: {p.name}  ({size:,} bytes)")

    state["baseline"] = baseline
    state["baseline_content"] = content_store
    state["last_checked_at"] = now
    print(f"\nBaseline recorded for {len(baseline)} file(s).")
    return state


def cmd_check(state: dict) -> tuple[dict, list]:
    """Check for drift. Returns (updated_state, list_of_drift_items)."""
    baseline = {b["path"]: b for b in (state.get("baseline") or [])}
    if not baseline:
        print("No baseline recorded. Run --baseline first.")
        return state, []

    paths = state.get("monitored_paths") or DEFAULT_MONITORED
    drift = []
    now = datetime.now().isoformat()

    for path_str in paths:
        p = Path(path_str).expanduser()
        old = baseline.get(path_str)
        if not old:
            continue
        new_hash, new_size = sha256_file(p)
        old_hash = old["sha256"]
        old_size = old.get("size_bytes", 0)

        if new_hash == old_hash:
            continue  # No change

        change_type = classify_change(old_size, new_size, old_hash, new_hash)
        delta = new_size - old_size

        drift_entry = {
            "path": path_str,
            "detected_at": now,
            "change_type": change_type,
            "old_sha256": old_hash,
            "new_sha256": new_hash,
            "size_delta": delta,
            "decision": "pending",
        }
        drift.append(drift_entry)

    # Log to history
    history = state.get("drift_history") or []
    history.extend(drift)
    state["drift_history"] = history
    state["last_checked_at"] = now

    if not drift:
        print(f"✓ All {len(paths)} monitored files intact.")
    else:
        severity_icons = {
            "append_only": "⚠",
            "truncation": "🔴",
            "full_replacement": "🔴",
            "deletion": "🔴",
        }
        print(f"\n⚠ Drift detected in {len(drift)} file(s):")
        for d in drift:
            icon = severity_icons.get(d["change_type"], "⚠")
            pname = Path(d["path"]).name
            print(f"  {icon} {pname}: {d['change_type']}  "
                  f"(Δ{d['size_delta']:+,} bytes)")
        print("\nRun --accept PATH to accept, or --restore PATH to revert.")

    return state, drift


def cmd_restore(state: dict, path_str: str) -> dict:
    contents = {c["path"]: c for c in (state.get("baseline_content") or [])}
    stored = contents.get(path_str)
    if not stored:
        print(f"ERROR: No baseline content stored for {path_str}")
        sys.exit(1)
    p = Path(path_str).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(stored["content_b64"]))
    print(f"✓ Restored: {p} from baseline ({stored['stored_at'][:10]})")

    # Update drift history
    history = state.get("drift_history") or []
    for entry in reversed(history):
        if entry.get("path") == path_str and entry.get("decision") == "pending":
            entry["decision"] = "restored"
            entry["decided_at"] = datetime.now().isoformat()
            break
    state["drift_history"] = history
    return state


def cmd_accept(state: dict, path_str: str) -> dict:
    p = Path(path_str).expanduser()
    new_hash, new_size = sha256_file(p)
    now = datetime.now().isoformat()

    baseline = state.get("baseline") or []
    for entry in baseline:
        if entry["path"] == path_str:
            entry["sha256"] = new_hash
            entry["size_bytes"] = new_size
            entry["baselined_at"] = now
            break
    state["baseline"] = baseline

    # Update content store
    content_store = state.get("baseline_content") or []
    for entry in content_store:
        if entry["path"] == path_str and p.exists():
            entry["content_b64"] = base64.b64encode(p.read_bytes()).decode()
            entry["stored_at"] = now
    state["baseline_content"] = content_store

    # Mark pending drift as accepted
    history = state.get("drift_history") or []
    for entry in reversed(history):
        if entry.get("path") == path_str and entry.get("decision") == "pending":
            entry["decision"] = "accepted"
            entry["decided_at"] = now
            break
    state["drift_history"] = history

    print(f"✓ Accepted: {Path(path_str).name} — baseline updated")
    return state


def cmd_status(state: dict) -> None:
    paths = state.get("monitored_paths") or DEFAULT_MONITORED
    baseline = {b["path"]: b for b in (state.get("baseline") or [])}
    pending = [d for d in (state.get("drift_history") or [])
               if d.get("decision") == "pending"]

    print(f"\nWorkspace Integrity Guardian")
    print(f"{'─' * 40}")
    print(f"Monitoring: {len(paths)} file(s)")
    print(f"Baseline:   {'recorded' if baseline else 'NOT recorded — run --baseline'}")
    print(f"Last check: {state.get('last_checked_at', 'never')[:19]}")
    print(f"Pending:    {len(pending)} unresolved drift(s)")
    print()
    for path_str in paths:
        p = Path(path_str).expanduser()
        b = baseline.get(path_str)
        exists = "✓" if p.exists() else "✗ MISSING"
        baselined = f"baselined {b['baselined_at'][:10]}" if b else "no baseline"
        print(f"  {exists}  {p.name}  ({baselined})")
    print()


def main():
    parser = argparse.ArgumentParser(description="Workspace integrity guardian")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--restore", metavar="PATH")
    group.add_argument("--accept", metavar="PATH")
    group.add_argument("--add-file", metavar="PATH")
    group.add_argument("--remove-file", metavar="PATH")
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()

    state = load_state()

    if args.add_file:
        paths = state.get("monitored_paths") or list(DEFAULT_MONITORED)
        p = str(Path(args.add_file).expanduser())
        if p not in paths:
            paths.append(p)
            state["monitored_paths"] = paths
            print(f"Added to monitoring: {p}")
            save_state(state)
        else:
            print(f"Already monitored: {p}")
        return

    if args.remove_file:
        paths = state.get("monitored_paths") or []
        p = str(Path(args.remove_file).expanduser())
        state["monitored_paths"] = [x for x in paths if x != p]
        print(f"Removed from monitoring: {p}")
        save_state(state)
        return

    if args.status:
        cmd_status(state)
        return

    if args.baseline:
        state = cmd_baseline(state)
    elif args.check:
        state, drift = cmd_check(state)
        if drift:
            sys.exit(1)
    elif args.restore:
        state = cmd_restore(state, args.restore)
    elif args.accept:
        state = cmd_accept(state, args.accept)

    save_state(state)


if __name__ == "__main__":
    main()
