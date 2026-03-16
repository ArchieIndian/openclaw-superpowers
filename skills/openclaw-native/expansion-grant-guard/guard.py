#!/usr/bin/env python3
"""Expansion Grant Guard — YAML-based delegation grant ledger.

Issues, validates, and tracks scoped permission grants for sub-agent
expansions with token budgets and auto-expiry.

Usage:
    python3 guard.py --issue --scope "dag-recall" --budget 4000 --ttl 30
    python3 guard.py --validate <grant-id>
    python3 guard.py --consume <grant-id> --tokens 500
    python3 guard.py --revoke <grant-id>
    python3 guard.py --list
    python3 guard.py --sweep
    python3 guard.py --audit
    python3 guard.py --stats
    python3 guard.py --status
    python3 guard.py --format json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

OPENCLAW_DIR = Path.home() / ".openclaw"
STATE_DIR = OPENCLAW_DIR / "skill-state" / "expansion-grant-guard"
LEDGER_PATH = STATE_DIR / "ledger.yaml"
STATE_PATH = STATE_DIR / "state.yaml"

DEFAULT_TTL_MINUTES = 30
MAX_TTL_MINUTES = 1440  # 24 hours
DEFAULT_BUDGET = 4000
MAX_HISTORY = 50


# ── YAML-lite read/write ────────────────────────────────────────────────────

def load_ledger():
    """Load the grant ledger from YAML-like file."""
    if not LEDGER_PATH.exists():
        return {"grants": [], "counter": 0}
    try:
        text = LEDGER_PATH.read_text()
        data = json.loads(text)  # stored as JSON for reliability
        return data
    except Exception:
        return {"grants": [], "counter": 0}


def save_ledger(ledger):
    """Save ledger to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str))


def load_state():
    """Load aggregate state."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {
        "total_issued": 0,
        "total_expired": 0,
        "total_revoked": 0,
        "total_exhausted": 0,
        "total_tokens_granted": 0,
        "total_tokens_consumed": 0,
        "grant_history": [],
    }


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Trim history
    if len(state.get("grant_history", [])) > MAX_HISTORY:
        state["grant_history"] = state["grant_history"][-MAX_HISTORY:]
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


# ── Grant operations ─────────────────────────────────────────────────────────

def generate_grant_id(ledger):
    """Generate a sequential grant ID for today."""
    counter = ledger.get("counter", 0) + 1
    ledger["counter"] = counter
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"g-{today}-{counter:03d}"


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(s):
    """Parse ISO datetime string."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def is_expired(grant):
    """Check if a grant has expired."""
    expires = parse_iso(grant.get("expires_at", ""))
    if expires and now_utc() > expires:
        return True
    return False


def is_exhausted(grant):
    """Check if token budget is consumed."""
    return grant.get("tokens_consumed", 0) >= grant.get("token_budget", 0)


def effective_status(grant):
    """Compute effective status considering time and budget."""
    if grant.get("status") in ("revoked",):
        return "revoked"
    if is_expired(grant):
        return "expired"
    if is_exhausted(grant):
        return "exhausted"
    return grant.get("status", "active")


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_issue(args):
    """Issue a new grant."""
    ledger = load_ledger()
    state = load_state()

    ttl = min(args.ttl, MAX_TTL_MINUTES)
    budget = args.budget

    grant_id = generate_grant_id(ledger)
    issued = now_utc()
    expires = issued + timedelta(minutes=ttl)

    grant = {
        "grant_id": grant_id,
        "scope": args.scope,
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "token_budget": budget,
        "tokens_consumed": 0,
        "status": "active",
        "issuer": args.issuer or "parent-session",
        "metadata": {},
    }
    if args.reason:
        grant["metadata"]["reason"] = args.reason

    ledger["grants"].append(grant)
    save_ledger(ledger)

    state["total_issued"] = state.get("total_issued", 0) + 1
    state["total_tokens_granted"] = state.get("total_tokens_granted", 0) + budget
    save_state(state)

    if args.format == "json":
        print(json.dumps(grant, indent=2))
    else:
        print("Grant Issued")
        print("─" * 50)
        print(f"  Grant ID:     {grant_id}")
        print(f"  Scope:        {args.scope}")
        print(f"  Token budget: {budget:,}")
        print(f"  Expires:      {expires.isoformat()} (in {ttl} min)")
        print(f"  Status:       active")
    return 0


def cmd_validate(args):
    """Validate a grant — check active, not expired, budget remaining."""
    ledger = load_ledger()
    grant = None
    for g in ledger["grants"]:
        if g["grant_id"] == args.validate:
            grant = g
            break

    if not grant:
        print(f"Grant not found: {args.validate}")
        return 1

    status = effective_status(grant)
    remaining = grant["token_budget"] - grant["tokens_consumed"]
    expires = parse_iso(grant["expires_at"])
    ttl_remaining = (expires - now_utc()).total_seconds() / 60 if expires else 0

    valid = status == "active"

    if args.format == "json":
        print(json.dumps({
            "grant_id": grant["grant_id"],
            "valid": valid,
            "status": status,
            "scope": grant["scope"],
            "tokens_remaining": max(0, remaining),
            "minutes_remaining": max(0, round(ttl_remaining, 1)),
        }, indent=2))
    else:
        icon = "✓" if valid else "✗"
        print(f"{icon} Grant: {grant['grant_id']}")
        print(f"  Status:           {status}")
        print(f"  Scope:            {grant['scope']}")
        print(f"  Tokens remaining: {max(0, remaining):,} / {grant['token_budget']:,}")
        if ttl_remaining > 0:
            print(f"  Expires in:       {max(0, round(ttl_remaining, 1))} min")
        else:
            print(f"  Expired:          {grant['expires_at']}")

    return 0 if valid else 1


def cmd_consume(args):
    """Record token consumption against a grant."""
    ledger = load_ledger()
    state = load_state()

    grant = None
    for g in ledger["grants"]:
        if g["grant_id"] == args.consume:
            grant = g
            break

    if not grant:
        print(f"Grant not found: {args.consume}")
        return 1

    status = effective_status(grant)
    if status != "active":
        print(f"Grant {args.consume} is {status} — cannot consume")
        return 1

    remaining = grant["token_budget"] - grant["tokens_consumed"]
    if args.tokens > remaining:
        print(f"Insufficient budget: requested {args.tokens}, remaining {remaining}")
        return 1

    grant["tokens_consumed"] += args.tokens
    state["total_tokens_consumed"] = state.get("total_tokens_consumed", 0) + args.tokens

    # Check if now exhausted
    if grant["tokens_consumed"] >= grant["token_budget"]:
        grant["status"] = "exhausted"
        state["total_exhausted"] = state.get("total_exhausted", 0) + 1
        close_grant(state, grant, "exhausted")

    save_ledger(ledger)
    save_state(state)

    new_remaining = grant["token_budget"] - grant["tokens_consumed"]
    if args.format == "json":
        print(json.dumps({
            "grant_id": grant["grant_id"],
            "tokens_consumed": args.tokens,
            "tokens_remaining": new_remaining,
            "status": effective_status(grant),
        }, indent=2))
    else:
        print(f"Consumed {args.tokens:,} tokens from {grant['grant_id']}")
        print(f"  Remaining: {new_remaining:,} / {grant['token_budget']:,}")
        if new_remaining == 0:
            print(f"  Status: exhausted")
    return 0


def cmd_revoke(args):
    """Revoke a grant early."""
    ledger = load_ledger()
    state = load_state()

    grant = None
    for g in ledger["grants"]:
        if g["grant_id"] == args.revoke:
            grant = g
            break

    if not grant:
        print(f"Grant not found: {args.revoke}")
        return 1

    if grant["status"] == "revoked":
        print(f"Grant {args.revoke} is already revoked")
        return 0

    grant["status"] = "revoked"
    state["total_revoked"] = state.get("total_revoked", 0) + 1
    close_grant(state, grant, "revoked")

    save_ledger(ledger)
    save_state(state)

    if args.format == "json":
        print(json.dumps({"grant_id": grant["grant_id"], "status": "revoked"}, indent=2))
    else:
        print(f"Revoked grant: {grant['grant_id']}")
    return 0


def cmd_list(args):
    """List active grants."""
    ledger = load_ledger()
    active = [g for g in ledger["grants"] if effective_status(g) == "active"]

    if args.format == "json":
        print(json.dumps(active, indent=2))
    else:
        print(f"Active Grants: {len(active)}")
        print("─" * 60)
        if not active:
            print("  No active grants")
        for g in active:
            remaining = g["token_budget"] - g["tokens_consumed"]
            expires = parse_iso(g["expires_at"])
            ttl = (expires - now_utc()).total_seconds() / 60 if expires else 0
            print(f"  {g['grant_id']}  scope={g['scope']}  "
                  f"tokens={remaining:,}/{g['token_budget']:,}  "
                  f"expires={max(0, round(ttl))}min")
    return 0


def cmd_sweep(args):
    """Clean up expired grants."""
    ledger = load_ledger()
    state = load_state()
    swept = 0

    for g in ledger["grants"]:
        if g["status"] == "active" and is_expired(g):
            g["status"] = "expired"
            state["total_expired"] = state.get("total_expired", 0) + 1
            close_grant(state, g, "expired")
            swept += 1

    save_ledger(ledger)
    save_state(state)

    if args.format == "json":
        print(json.dumps({"swept": swept}, indent=2))
    else:
        print(f"Sweep complete: {swept} grants expired")
    return 0


def cmd_audit(args):
    """Show full audit log."""
    state = load_state()
    history = state.get("grant_history", [])

    if args.format == "json":
        print(json.dumps(history, indent=2))
    else:
        print(f"Grant Audit Log: {len(history)} entries")
        print("─" * 65)
        for h in reversed(history[-20:]):
            print(f"  {h['grant_id']}  scope={h['scope']}  "
                  f"status={h['final_status']}  "
                  f"tokens={h['tokens_consumed']}/{h['token_budget']}  "
                  f"closed={h.get('closed_at', '?')[:16]}")
    return 0


def cmd_stats(args):
    """Show grant statistics."""
    state = load_state()
    ledger = load_ledger()
    active_count = sum(1 for g in ledger["grants"] if effective_status(g) == "active")

    if args.format == "json":
        stats = {
            "active_grants": active_count,
            "total_issued": state.get("total_issued", 0),
            "total_expired": state.get("total_expired", 0),
            "total_revoked": state.get("total_revoked", 0),
            "total_exhausted": state.get("total_exhausted", 0),
            "total_tokens_granted": state.get("total_tokens_granted", 0),
            "total_tokens_consumed": state.get("total_tokens_consumed", 0),
        }
        print(json.dumps(stats, indent=2))
    else:
        print("Expansion Grant Statistics")
        print("─" * 50)
        print(f"  Active grants:      {active_count}")
        print(f"  Total issued:       {state.get('total_issued', 0)}")
        print(f"  Total expired:      {state.get('total_expired', 0)}")
        print(f"  Total revoked:      {state.get('total_revoked', 0)}")
        print(f"  Total exhausted:    {state.get('total_exhausted', 0)}")
        tg = state.get('total_tokens_granted', 0)
        tc = state.get('total_tokens_consumed', 0)
        print(f"  Tokens granted:     {tg:,}")
        print(f"  Tokens consumed:    {tc:,}")
        if tg > 0:
            pct = round(tc / tg * 100, 1)
            print(f"  Utilization:        {pct}%")
    return 0


def cmd_status(args):
    """Show current status summary."""
    state = load_state()
    ledger = load_ledger()
    active = [g for g in ledger["grants"] if effective_status(g) == "active"]

    if args.format == "json":
        print(json.dumps({
            "active_grants": len(active),
            "total_issued": state.get("total_issued", 0),
            "total_tokens_consumed": state.get("total_tokens_consumed", 0),
        }, indent=2))
    else:
        print("Expansion Grant Guard — Status")
        print("─" * 50)
        print(f"  Active grants:      {len(active)}")
        print(f"  Total issued:       {state.get('total_issued', 0)}")
        print(f"  Tokens consumed:    {state.get('total_tokens_consumed', 0):,}")
        if active:
            print()
            for g in active[:5]:
                remaining = g["token_budget"] - g["tokens_consumed"]
                print(f"  {g['grant_id']}  {g['scope']}  {remaining:,} tokens remaining")
    return 0


# ── Helpers ──────────────────────────────────────────────────────────────────

def close_grant(state, grant, final_status):
    """Record a closed grant in history."""
    entry = {
        "grant_id": grant["grant_id"],
        "scope": grant["scope"],
        "issued_at": grant["issued_at"],
        "closed_at": now_utc().isoformat(),
        "token_budget": grant["token_budget"],
        "tokens_consumed": grant["tokens_consumed"],
        "final_status": final_status,
    }
    history = state.get("grant_history", [])
    history.append(entry)
    state["grant_history"] = history


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Expansion Grant Guard — delegation grant ledger"
    )
    parser.add_argument("--issue", action="store_true", help="Issue a new grant")
    parser.add_argument("--validate", type=str, help="Validate a grant by ID")
    parser.add_argument("--consume", type=str, help="Consume tokens from a grant")
    parser.add_argument("--revoke", type=str, help="Revoke a grant")
    parser.add_argument("--list", action="store_true", help="List active grants")
    parser.add_argument("--sweep", action="store_true", help="Clean up expired grants")
    parser.add_argument("--audit", action="store_true", help="Show audit log")
    parser.add_argument("--stats", action="store_true", help="Grant statistics")
    parser.add_argument("--status", action="store_true", help="Current status")
    # Issue options
    parser.add_argument("--scope", type=str, default="general", help="Grant scope")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="Token budget")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_MINUTES, help="TTL in minutes")
    parser.add_argument("--issuer", type=str, help="Grant issuer identifier")
    parser.add_argument("--reason", type=str, help="Reason for grant")
    # Consume options
    parser.add_argument("--tokens", type=int, default=0, help="Tokens to consume")
    # Output
    parser.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args()

    if args.issue:
        return cmd_issue(args)
    elif args.validate:
        return cmd_validate(args)
    elif args.consume:
        return cmd_consume(args)
    elif args.revoke:
        return cmd_revoke(args)
    elif args.list:
        return cmd_list(args)
    elif args.sweep:
        return cmd_sweep(args)
    elif args.audit:
        return cmd_audit(args)
    elif args.stats:
        return cmd_stats(args)
    elif args.status:
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
