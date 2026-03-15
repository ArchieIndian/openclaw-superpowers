#!/usr/bin/env python3
"""
Obsidian Sync for OpenClaw.

Copies OpenClaw memory files into an Obsidian vault for human-readable
knowledge management. Reads vault path from state.yaml.

Synced files:
  ~/.openclaw/memory/MEMORY.md       → <vault>/OpenClaw/Memory.md
  ~/.openclaw/memory/YYYY-MM-DD.md   → <vault>/OpenClaw/Daily/YYYY-MM-DD.md

Usage:
    python3 sync.py                          # Run sync (idempotent)
    python3 sync.py --vault /path/to/vault   # Override vault path
    python3 sync.py --dry-run                # Show what would be copied
    python3 sync.py --all-daily              # Sync all daily files, not just today's
    python3 sync.py --set-vault /path        # Save vault path to state and exit
"""

import argparse
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
MEMORY_DIR = OPENCLAW_DIR / "memory"
STATE_FILE = OPENCLAW_DIR / "skill-state" / "obsidian-sync" / "state.yaml"


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        text = STATE_FILE.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or {}
        # Flat fallback
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if line and ":" in line and not line.startswith("#"):
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result
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
                f.write(f"{k}: {v}\n")


# ── Sync logic ────────────────────────────────────────────────────────────────

def sync_file(src: Path, dst: Path, dry_run: bool) -> bool:
    """Copy src to dst, creating parent dirs. Returns True if copied."""
    if not src.exists():
        return False
    if dst.exists():
        # Skip if identical
        if src.read_bytes() == dst.read_bytes():
            return False
    if dry_run:
        print(f"  [dry-run] Would copy: {src} → {dst}")
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  ✓ Synced: {src.name} → {dst}")
    return True


def run_sync(vault_path: Path, sync_all_daily: bool, dry_run: bool) -> dict:
    """Run sync and return result stats."""
    vault_openclaw = vault_path / "OpenClaw"
    vault_daily = vault_openclaw / "Daily"

    copied = 0
    skipped = 0

    print(f"\nSyncing to vault: {vault_path}")
    print(f"{'─' * 40}")

    # Sync MEMORY.md
    memory_src = MEMORY_DIR / "MEMORY.md"
    memory_dst = vault_openclaw / "Memory.md"
    if sync_file(memory_src, memory_dst, dry_run):
        copied += 1
    else:
        skipped += 1
        if not memory_src.exists():
            print(f"  (no MEMORY.md found at {memory_src})")

    # Sync daily files
    if MEMORY_DIR.exists():
        today_str = str(date.today())
        for daily_file in sorted(MEMORY_DIR.glob("????-??-??.md")):
            # Only sync today's file unless --all-daily
            if not sync_all_daily and daily_file.stem != today_str:
                continue
            dst = vault_daily / daily_file.name
            if sync_file(daily_file, dst, dry_run):
                copied += 1
            else:
                skipped += 1
    else:
        print(f"  (memory directory not found at {MEMORY_DIR})")

    print(f"\n{copied} file(s) synced, {skipped} already up to date.")
    return {"copied": copied, "skipped": skipped}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync OpenClaw memory to Obsidian vault")
    parser.add_argument("--vault", metavar="PATH", help="Path to Obsidian vault (overrides state)")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without copying")
    parser.add_argument("--all-daily", action="store_true", help="Sync all daily files, not just today")
    parser.add_argument("--set-vault", metavar="PATH", help="Save vault path to state and exit")
    args = parser.parse_args()

    state = load_state()

    if args.set_vault:
        vault_path = Path(args.set_vault).expanduser().resolve()
        if not vault_path.exists():
            print(f"WARNING: Vault path does not exist yet: {vault_path}")
        state["vault_path"] = str(vault_path)
        save_state(state)
        print(f"Vault path saved: {vault_path}")
        print(f"State: {STATE_FILE}")
        sys.exit(0)

    # Resolve vault path
    vault_raw = args.vault or state.get("vault_path", "")
    if not vault_raw:
        print("ERROR: No vault path configured.")
        print("  Set it with: python3 sync.py --set-vault /path/to/vault")
        print("  Or pass --vault /path/to/vault")
        sys.exit(1)

    vault_path = Path(vault_raw).expanduser().resolve()
    if not vault_path.exists() and not args.dry_run:
        print(f"ERROR: Vault path does not exist: {vault_path}")
        print("  Create the vault in Obsidian first, or use --dry-run to preview.")
        sys.exit(1)

    result = run_sync(vault_path, args.all_daily, args.dry_run)

    if not args.dry_run:
        state.update(
            {
                "vault_path": str(vault_path),
                "last_synced_at": datetime.now().isoformat(),
                "files_synced": result["copied"],
                "status": "synced",
            }
        )
        save_state(state)


if __name__ == "__main__":
    main()
