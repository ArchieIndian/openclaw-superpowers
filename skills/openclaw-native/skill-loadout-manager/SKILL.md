---
name: skill-loadout-manager
version: "1.0"
category: openclaw-native
description: Manages named skill profiles (loadouts) so you can switch between focused skill sets and prevent system prompt bloat from too many active skills.
stateful: true
---

# Skill Loadout Manager

## What it does

Installing more skills increases OpenClaw's system prompt size. Every installed skill contributes its description to the context window on every session start — even skills you haven't used in months.

Skill Loadout Manager lets you define named loadouts: curated subsets of skills for specific contexts. You switch to a loadout and only those skills are active. Everything else is installed but dormant.

Examples:
- `coding` — tools for writing, testing, reviewing code
- `research` — browsing, fact-checking, note synthesis
- `ops` — monitoring, cron hygiene, spend tracking
- `minimal` — just the essentials: memory, handoff, recovery

## When to invoke

- When you notice system prompt bloat slowing context initialisation
- When switching between focused work modes (deep coding vs. research)
- When you want to test a single skill in isolation
- After adding many new skills that aren't always relevant

## Loadout structure

A loadout is a named list of skill names stored in state. Activating a loadout signals to OpenClaw's skill loader which skills to surface in the system prompt. Skills not in the active loadout remain installed but excluded from description injection.

```yaml
# Example loadout definition
name: coding
skills:
  - systematic-debugging
  - test-driven-development
  - verification-before-completion
  - skill-doctor
  - dangerous-action-guard
```

## How to use

```bash
python3 loadout.py --list                      # Show all loadouts and active one
python3 loadout.py --create coding             # Create new loadout (interactive)
python3 loadout.py --add coding skill-doctor   # Add skill to loadout
python3 loadout.py --remove coding skill-doctor  # Remove skill
python3 loadout.py --activate coding           # Switch to loadout
python3 loadout.py --activate --all            # Activate all skills
python3 loadout.py --show coding               # List skills in a loadout
python3 loadout.py --status                    # Current active loadout
python3 loadout.py --estimate coding           # Estimate token savings
```

## Procedure

**Step 1 — Assess current footprint**

```bash
python3 loadout.py --estimate --all
```

This shows the estimated description token count for all installed skills and highlights candidates for loadout pruning.

**Step 2 — Define your loadouts**

Think in contexts: What skills do you actually need when writing code? When doing research? During maintenance windows? Create one loadout per context, aiming for 5–10 skills each.

```bash
python3 loadout.py --create coding
python3 loadout.py --add coding systematic-debugging test-driven-development
python3 loadout.py --add coding verification-before-completion dangerous-action-guard
```

**Step 3 — Activate a loadout**

```bash
python3 loadout.py --activate coding
```

OpenClaw reads the active loadout from state on next session start and only injects those skill descriptions.

**Step 4 — Switch as needed**

Switching is instant and takes effect on the next session. No restart required.

**Step 5 — Return to full mode**

```bash
python3 loadout.py --activate --all
```

## State

Active loadout name and all loadout definitions stored in `~/.openclaw/skill-state/skill-loadout-manager/state.yaml`.

Fields: `active_loadout`, `loadouts` map, `switch_history`.

## Notes

- Always-on skills (e.g., `dangerous-action-guard`, `prompt-injection-guard`) can be marked `pinned: true` so they're included in every loadout automatically.
- The `minimal` loadout is pre-seeded at install time with only safety and recovery skills.
