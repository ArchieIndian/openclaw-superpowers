---
name: secrets-hygiene
description: Audits which skills have access to secrets, flags stale or unrotated credentials, and prompts rotation. Use weekly to keep credentials clean.
cron: "0 9 * * 1"
stateful: true
---

# Secrets Hygiene

State file: `~/.openclaw/skill-state/secrets-hygiene/state.yaml`

Credentials you forgot about are credentials that will leak.

## When to Use

- On Monday 9am cron wakeup
- When adding or removing a skill that uses credentials
- After any suspected security incident

## The Audit Process

### Step 1: Inventory
List all secrets currently configured in OpenClaw (env vars, config files, keychain entries referenced by installed skills). For each, record: name, which skills access it, when it was last rotated (if known).

### Step 2: Flag Stale Secrets
A secret is stale if:
- Last rotated more than 90 days ago (or unknown rotation date)
- The skill that uses it is no longer installed
- It grants broader access than the skill needs

### Step 3: Report
Send a summary:
```
Secrets Audit — [date]
[N] secrets tracked
[N] flagged for rotation: [names]
[N] orphaned (skill removed): [names]
Action needed: [yes/no]
```

### Step 4: Update State
Write `last_audit_at`, updated `tracked_secrets` list, `flagged_count`, `orphaned_count` to state file.

## Cron Wakeup Behavior

On Monday 9am wakeup:
- Read state; if `last_audit_at` is within the last 6 days, skip
- Otherwise run the audit and update state
