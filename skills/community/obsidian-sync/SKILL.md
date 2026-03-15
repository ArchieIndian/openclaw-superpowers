---
name: obsidian-sync
description: Syncs agent daily memory and MEMORY.md to an Obsidian vault so notes are human-browsable. Use nightly or on demand.
cron: "0 22 * * *"
stateful: true
---

# Obsidian Sync

State file: `~/.openclaw/skill-state/obsidian-sync/state.yaml`

Your agent's memory should be readable by you, not just by the agent.

## When to Use

- On 10pm nightly cron wakeup
- When the user asks to sync notes to Obsidian
- After a major task completion worth archiving

## Setup (First Run)

On first run, ask the user for their vault path and write it to state as `vault_path`. Do not proceed until this is set.

## The Sync Process

### Step 1: Read Agent Memory
- Read today's `memory/YYYY-MM-DD.md`
- Read `MEMORY.md` (long-term memory)

### Step 2: Write to Vault
- Copy `memory/YYYY-MM-DD.md` → `<vault_path>/OpenClaw/Daily/YYYY-MM-DD.md`
- Copy `MEMORY.md` → `<vault_path>/OpenClaw/Memory.md`
- Create `<vault_path>/OpenClaw/` directory if it doesn't exist

### Step 3: Update State
Write `last_sync_at`, `notes_written` (count of files written), `vault_path` to state.

## Cron Wakeup Behavior

On 10pm wakeup:
- Check `vault_path` in state — if empty, skip and notify user to set it
- Check `last_sync_at` — if today, skip
- Otherwise run sync

## Key Principles

- Never overwrite vault files the user has manually edited — append-only to Daily notes
- If the vault path doesn't exist, warn the user rather than creating it silently
- Keep the OpenClaw folder structure flat and simple
