#!/usr/bin/env python3
from __future__ import annotations

"""
Message Delivery Verifier for openclaw-superpowers.

Tracks the last-mile state of outbound notifications across supported channels.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from state_helpers import load_state as load_state_file
from state_helpers import now_iso, save_state as save_state_file, skill_state_file

STATE_FILE = skill_state_file("message-delivery-verifier")
MAX_DELIVERIES = 200
MAX_HISTORY = 12
STALE_AFTER_MINUTES = 60


def default_state() -> dict:
    return {
        "deliveries": [],
        "stale_deliveries": [],
        "last_report_at": "",
        "report_history": [],
    }


def load_state() -> dict:
    return load_state_file(STATE_FILE, default_state)


def save_state(state: dict) -> None:
    save_state_file(STATE_FILE, state)


def find_delivery(state: dict, delivery_id: str) -> dict | None:
    for item in state.get("deliveries", []):
        if item.get("delivery_id") == delivery_id:
            return item
    return None


def ensure_delivery(state: dict, channel: str, delivery_id: str, recipient: str = "", body: str = "") -> dict:
    existing = find_delivery(state, delivery_id)
    if existing:
        return existing
    entry = {
        "channel": channel,
        "delivery_id": delivery_id,
        "recipient": recipient,
        "body": body,
        "queued_at": now_iso(),
        "sent_at": "",
        "acknowledged_at": "",
        "status": "queued",
        "receipt": "",
        "failure_reason": "",
        "retry_count": 0,
    }
    state["deliveries"] = [entry] + (state.get("deliveries") or [])
    state["deliveries"] = state["deliveries"][:MAX_DELIVERIES]
    return entry


def refresh_stale(state: dict) -> None:
    stale = []
    current = datetime.now()
    for item in state.get("deliveries", []):
        if item.get("status") in {"acknowledged", "failed"}:
            continue
        ts = item.get("sent_at") or item.get("queued_at")
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
                    "delivery_id": item.get("delivery_id", ""),
                    "channel": item.get("channel", ""),
                    "recipient": item.get("recipient", ""),
                    "age_minutes": age,
                }
            )
    state["stale_deliveries"] = stale


def record_history(state: dict) -> None:
    refresh_stale(state)
    history = state.get("report_history") or []
    history.insert(
        0,
        {
            "reported_at": now_iso(),
            "total_deliveries": len(state.get("deliveries", [])),
            "stale_count": len(state.get("stale_deliveries", [])),
            "failed_count": sum(1 for item in state.get("deliveries", []) if item.get("status") == "failed"),
        },
    )
    state["last_report_at"] = history[0]["reported_at"]
    state["report_history"] = history[:MAX_HISTORY]


def print_report(state: dict, stale_only: bool = False) -> None:
    refresh_stale(state)
    deliveries = state.get("deliveries", [])
    stale = state.get("stale_deliveries", [])
    failed_count = sum(1 for item in deliveries if item.get("status") == "failed")
    print("\nMessage Delivery Verifier")
    print("───────────────────────────────────────────────────────")
    print(f"  {len(deliveries)} deliveries | {len(stale)} stale | {failed_count} failed")
    if stale_only:
        for item in stale:
            print(f"  STALE {item['channel']} {item['delivery_id']} -> {item['recipient']}")
        if not stale:
            print("\n  No stale deliveries.")
        return
    if not deliveries:
        print("\n  No deliveries recorded.")
        return
    for item in deliveries[:10]:
        print(f"  {item.get('status', '').upper():12} {item.get('channel', '')} {item.get('delivery_id', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track outbound message delivery state")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--queue", metavar="CHANNEL", help="Queue a delivery")
    group.add_argument("--sent", metavar="CHANNEL", help="Mark a delivery sent")
    group.add_argument("--ack", metavar="CHANNEL", help="Mark a delivery acknowledged")
    group.add_argument("--fail", metavar="CHANNEL", help="Mark a delivery failed")
    group.add_argument("--stale", action="store_true", help="Show stale deliveries")
    group.add_argument("--report", action="store_true", help="Show delivery report")
    parser.add_argument("--delivery-id", help="Stable delivery identifier")
    parser.add_argument("--recipient", default="", help="Channel recipient")
    parser.add_argument("--body", default="", help="Message body")
    parser.add_argument("--receipt", default="", help="Provider receipt or message ID")
    parser.add_argument("--reason", default="", help="Failure reason")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    state = load_state()
    if args.queue:
        delivery_id = args.delivery_id or f"{args.queue}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ensure_delivery(state, args.queue, delivery_id, args.recipient, args.body)
        save_state(state)
    elif args.sent:
        if not args.delivery_id:
            raise SystemExit("--delivery-id is required for --sent")
        entry = ensure_delivery(state, args.sent, args.delivery_id, args.recipient, args.body)
        entry["sent_at"] = now_iso()
        entry["status"] = "sent"
        entry["receipt"] = args.receipt or entry.get("receipt", "")
        save_state(state)
    elif args.ack:
        if not args.delivery_id:
            raise SystemExit("--delivery-id is required for --ack")
        entry = ensure_delivery(state, args.ack, args.delivery_id)
        entry["acknowledged_at"] = now_iso()
        entry["status"] = "acknowledged"
        save_state(state)
    elif args.fail:
        if not args.delivery_id:
            raise SystemExit("--delivery-id is required for --fail")
        entry = ensure_delivery(state, args.fail, args.delivery_id)
        entry["status"] = "failed"
        entry["failure_reason"] = args.reason
        entry["retry_count"] = int(entry.get("retry_count", 0)) + 1
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
