---
name: skill-doctor
version: "1.0"
category: openclaw-native
description: Diagnoses silent skill discovery failures — YAML parse errors, path violations, schema mismatches — so broken skills don't disappear without a trace.
stateful: true
---

# Skill Doctor

## What it does

OpenClaw loads skills at startup. When a skill fails to load — corrupt frontmatter, bad cron expression, mismatched STATE_SCHEMA — it silently disappears from the registry. There is no error surfaced to the agent.

Skill Doctor runs a full diagnostic pass over all installed skills and reports every failure that would cause silent non-loading, so you can fix problems before they become invisible gaps.

## When to invoke

- After installing new skills or upgrading openclaw-superpowers
- When a skill you expect to find is missing from the registry
- As a post-install gate inside `install.sh`
- Manually, any time something feels off with skill behaviour

## Diagnostic checks

Skill Doctor runs 6 checks per skill:

| Check | Failure condition |
|---|---|
| YAML parse | Frontmatter cannot be parsed by a YAML parser |
| Required fields | `name` or `description` absent from frontmatter |
| Path conventions | Skill directory name does not match `name:` field |
| Cron format | `cron:` present but not a valid 5-field cron expression |
| Stateful coherence | `stateful: true` but `STATE_SCHEMA.yaml` missing |
| Schema validity | `STATE_SCHEMA.yaml` present but missing `version:` or `fields:` |

## Output levels

- **PASS** — skill will load correctly
- **WARN** — skill loads but has a non-critical issue (e.g. schema present but `stateful:` missing)
- **FAIL** — skill will not load; must fix before use

## How to use

```
python3 doctor.py --scan                   # Full diagnostic pass
python3 doctor.py --scan --only-failures   # Show FAILs only
python3 doctor.py --scan --skill cron-hygiene   # Single skill
python3 doctor.py --fix-hint cron-hygiene  # Print actionable fix suggestion
python3 doctor.py --status                 # Summary of last scan
python3 doctor.py --format json            # Machine-readable output
```

## Procedure

**Step 1 — Run the scan**

```
python3 doctor.py --scan
```

Review the output. Each skill gets a one-line verdict: PASS / WARN / FAIL.

**Step 2 — Triage FAILs first**

For each FAIL, run `--fix-hint <skill-name>` to get an actionable repair suggestion. Skill Doctor never modifies skill files itself — it tells you exactly what to change.

**Step 3 — Review WARNs**

WARNs do not block loading but indicate drift from conventions. Common WARN: `STATE_SCHEMA.yaml` exists without `stateful: true` in frontmatter. Fix by adding the frontmatter field.

**Step 4 — Re-scan to confirm**

After applying fixes, re-run `--scan` and verify no FAILs remain.

**Step 5 — Write scan result to state**

After a clean pass, the scan summary is automatically written to state. Use `--status` in future sessions to surface the last known health without re-scanning.

## State

Skill Doctor persists scan results in `~/.openclaw/skill-state/skill-doctor/state.yaml`.

Fields: `last_scan_at`, `skills_scanned`, `fail_count`, `warn_count`, `violations` list.

After a clean install, `fail_count` and `warn_count` should both be 0.

## Integration

Add to the end of `install.sh`:

```bash
echo "Running Skill Doctor post-install check..."
python3 ~/.openclaw/extensions/superpowers/skills/openclaw-native/skill-doctor/doctor.py --scan --only-failures
```

This surfaces any broken skills immediately after install rather than letting them silently disappear.
