---
name: memory-integrity-checker
version: "1.0"
category: openclaw-native
description: Validates memory summary DAGs for structural integrity — detects orphan nodes, circular references, token inflation, broken lineage, and stale summaries that corrupt the agent's memory.
stateful: true
cron: "0 3 * * 0"
---

# Memory Integrity Checker

## What it does

As memory DAGs grow through compaction, they can develop structural problems: orphan nodes with no parent, circular reference loops, summaries that inflated instead of compressing, broken lineage chains, and stale nodes that should have been dissolved. These problems silently corrupt the agent's memory.

Memory Integrity Checker runs 8 structural checks on the DAG, generates a repair plan, and optionally auto-fixes safe issues.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s DAG integrity checking system, which detects and repairs corrupted summaries.

## When to invoke

- Automatically Sundays at 3am (cron) — weekly structural audit
- After a crash or unexpected shutdown — check for corruption
- When the agent's memory seems inconsistent — diagnose structural issues
- Before a major compaction or prune operation — ensure clean starting state

## Integrity checks (8 total)

| Check | What it detects | Severity |
|---|---|---|
| ORPHAN_NODE | Node with no parent and not a root | HIGH |
| CIRCULAR_REF | Circular parent-child loops in the DAG | CRITICAL |
| TOKEN_INFLATION | Summary has more tokens than its combined children | HIGH |
| BROKEN_LINEAGE | Edge references a node ID that doesn't exist | CRITICAL |
| STALE_ACTIVE | Active node older than 30 days with no children | MEDIUM |
| EMPTY_NODE | Node with empty or whitespace-only content | HIGH |
| DUPLICATE_EDGE | Same parent-child edge appears multiple times | LOW |
| DEPTH_MISMATCH | Node's depth doesn't match its position in the DAG | MEDIUM |

## How to use

```bash
python3 integrity.py --check                  # Run all 8 integrity checks
python3 integrity.py --check --fix            # Auto-fix safe issues
python3 integrity.py --check --only ORPHAN_NODE  # Run a specific check
python3 integrity.py --repair-plan            # Generate repair plan without fixing
python3 integrity.py --status                 # Last check summary
python3 integrity.py --format json            # Machine-readable output
```

## Procedure

**Step 1 — Run integrity checks**

```bash
python3 integrity.py --check
```

Runs all 8 checks and reports findings by severity.

**Step 2 — Review repair plan**

```bash
python3 integrity.py --repair-plan
```

For each finding, shows what the auto-fix would do:
- ORPHAN_NODE → reattach to nearest active root or deactivate
- DUPLICATE_EDGE → remove duplicates
- EMPTY_NODE → deactivate
- STALE_ACTIVE → deactivate

**Step 3 — Apply safe fixes**

```bash
python3 integrity.py --check --fix
```

Auto-fixes LOW and MEDIUM severity issues. HIGH and CRITICAL require manual review.

## State

Check results, finding history, and repair actions stored in `~/.openclaw/skill-state/memory-integrity-checker/state.yaml`.

Fields: `last_check_at`, `findings`, `check_history`, `repairs_applied`.

## Notes

- Reads from memory-dag-compactor's state file — does not maintain its own DAG
- Auto-fix only applies to LOW and MEDIUM severity issues
- CRITICAL issues (circular refs, broken lineage) require manual intervention
- Circular reference detection uses DFS with visited-set tracking
- Token inflation check compares parent tokens vs. sum of children tokens
