---
name: installed-skill-auditor
version: "1.0"
category: openclaw-native
description: Weekly audit of all installed third-party and community skills for malicious patterns, stale credentials, and drift from last-known-good state.
stateful: true
cron: "0 9 * * 1"
---

# Installed Skill Auditor

## What it does

`skill-vetting` scans before install. `installed-skill-auditor` scans after — continuously.

Skills can be modified after installation. A community skill that was safe on Monday can be compromised by Tuesday if the source repo is pushed to and your agent auto-pulls. This skill runs weekly to catch post-install drift: injected payloads, hardcoded credentials, and pattern changes that weren't there at install time.

It maintains a content hash of every skill file at the time it was first audited. On each weekly run it re-hashes and flags anything that changed unexpectedly.

## When to invoke

- Automatically, every Monday at 9am (cron)
- Manually after any `git pull` that touches skill directories
- After any agent action that writes to the skills tree

## Audit checks

| Check | What it detects |
|---|---|
| INJECTION | Instruction-override patterns in SKILL.md prose |
| CREDENTIAL | Hardcoded tokens, API keys, or secrets in any file |
| EXFILTRATION | URLs + data-sending patterns suggesting exfil |
| DRIFT | File content changed since last known-good baseline |
| ORPHAN | Skill directory present but not in install manifest |

Severity: CRITICAL (INJECTION, EXFILTRATION) · HIGH (CREDENTIAL) · MEDIUM (DRIFT, ORPHAN)

## Output

```
Installed Skill Audit — 2026-03-16
────────────────────────────────────────────
32 skills audited | 0 CRITICAL | 1 HIGH | 2 MEDIUM

HIGH     community/my-custom-skill — CREDENTIAL
         Hardcoded token pattern detected in run.py (line 14)

MEDIUM   community/expense-tracker — DRIFT
         SKILL.md hash changed since 2026-03-10 baseline
         Run: python3 audit.py --diff expense-tracker
```

## How to use

```
python3 audit.py --scan                    # Full audit pass
python3 audit.py --scan --critical-only    # CRITICAL findings only
python3 audit.py --baseline                # Record current state as trusted
python3 audit.py --diff <skill-name>       # Show changed lines since baseline
python3 audit.py --resolve <skill-name>    # Mark finding resolved after review
python3 audit.py --status                  # Summary of last run
python3 audit.py --format json             # Machine-readable output
```

## Procedure

**Step 1 — Review the report**

The cron run generates a report automatically. Open it via `--status` or check state. Any CRITICAL finding requires immediate action.

**Step 2 — Triage by severity**

- **CRITICAL**: Do not run the skill. Inspect the file, remove or quarantine the skill.
- **HIGH**: Rotate the exposed credential immediately; investigate how it got there.
- **MEDIUM (DRIFT)**: Use `--diff` to see what changed. If the change is expected (you updated the skill), run `--baseline` to accept it. If unexpected, treat as CRITICAL.
- **MEDIUM (ORPHAN)**: A skill directory exists with no install record. Either re-install through the vetting process or remove the directory.

**Step 3 — Resolve or escalate**

Run `--resolve <skill-name>` after reviewing a finding. This marks it acknowledged in state. Unresolved CRITICAL findings are surfaced again on next cron run.

**Step 4 — Update baseline after intentional changes**

When you intentionally update a skill (e.g., upgrading to a new version), run `--baseline` so future drift detection has an accurate reference point.

## State

Results and content hashes stored in `~/.openclaw/skill-state/installed-skill-auditor/state.yaml`.

Fields: `last_audit_at`, `baselines` (hash map), `findings`, `audit_history`.
