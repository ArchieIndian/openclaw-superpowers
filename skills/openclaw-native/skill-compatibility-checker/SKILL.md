---
name: skill-compatibility-checker
version: "1.0"
category: openclaw-native
description: Checks whether installed skills are compatible with the current OpenClaw version and flags skills that require runtime features not present in your installation.
stateful: true
---

# Skill Compatibility Checker

## What it does

Skills can declare minimum OpenClaw version requirements and depend on specific runtime features (cron engine, session isolation, state storage, context compaction). When you upgrade or downgrade OpenClaw, or move a skill to a different environment, compatibility silently breaks.

Skill Compatibility Checker reads skill frontmatter for version constraints and feature requirements, then compares them against the currently running OpenClaw version. It reports incompatibilities before they cause confusing silent failures.

## When to invoke

- After upgrading OpenClaw
- Before deploying a skill to a new environment
- When a skill that previously worked stops working after an update
- As a post-upgrade gate in automated deployment pipelines

## Frontmatter fields checked

```yaml
---
name: my-skill
requires_openclaw: ">=1.4.0"  # optional semver constraint
requires_features:             # optional list of runtime features
  - cron
  - session_isolation
  - state_storage
  - context_compaction
  - sessions_send
---
```

If these fields are absent the skill is treated as version-agnostic.

## Feature registry

| Feature | Introduced | Description |
|---|---|---|
| `cron` | 1.0.0 | Cron-scheduled skill wakeups |
| `state_storage` | 1.0.0 | Persistent skill state at `~/.openclaw/skill-state/` |
| `session_isolation` | 1.2.0 | Skills run in isolated sessions (not main session) |
| `context_compaction` | 1.3.0 | Native context compaction API |
| `sessions_send` | 1.4.0 | Cross-session message passing |

## Output

```
Skill Compatibility Check — OpenClaw 1.3.2
────────────────────────────────────────────────
32 skills checked | 0 incompatible | 2 warnings

WARN  channel-context-bridge: requires sessions_send (≥1.4.0, have 1.3.2)
WARN  multi-agent-coordinator: requires sessions_send (≥1.4.0, have 1.3.2)
```

## How to use

```bash
python3 check.py --check                   # Full compatibility scan
python3 check.py --check --skill my-skill  # Single skill
python3 check.py --openclaw-version 1.5.0  # Override detected version
python3 check.py --features                # List all known features + versions
python3 check.py --status                  # Last check summary
python3 check.py --format json
```

## Procedure

**Step 1 — Run the check**

```bash
python3 check.py --check
```

**Step 2 — Triage incompatibilities**

- **FAIL**: The skill cannot run on this version. Either upgrade OpenClaw or disable the skill.
- **WARN**: The skill declares a feature that may be available but wasn't present in the stated minimum. Functionality may be degraded.

**Step 3 — Document your constraints**

If you're writing a new skill that uses `sessions_send` or `session_isolation`, add the appropriate `requires_openclaw:` and `requires_features:` frontmatter so future users know immediately if their version supports it.

## State

Last check results stored in `~/.openclaw/skill-state/skill-compatibility-checker/state.yaml`.

Fields: `last_check_at`, `openclaw_version`, `incompatibilities`, `check_history`.
