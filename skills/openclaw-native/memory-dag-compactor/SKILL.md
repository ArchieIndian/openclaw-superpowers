---
name: memory-dag-compactor
version: "1.0"
category: openclaw-native
description: Builds hierarchical summary DAGs from MEMORY.md with depth-aware prompts — leaf summaries preserve detail, higher depths condense to durable arcs, preventing information loss during compaction.
stateful: true
cron: "0 23 * * *"
---

# Memory DAG Compactor

## What it does

Standard memory compaction is lossy — older entries get truncated and details disappear forever. Memory DAG Compactor replaces flat compaction with a **directed acyclic graph (DAG)** of hierarchical summaries inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s Lossless Context Management approach.

Each depth in the DAG uses a purpose-built prompt tuned for that abstraction level:

| Depth | Name | What it preserves | Timeline granularity |
|---|---|---|---|
| d0 | Leaf | File operations, timestamps, specific actions, errors | Hours |
| d1 | Condensed | What changed vs. previous context, decisions made | Sessions |
| d2 | Arc | Goal → outcome → carries forward | Days |
| d3+ | Durable | Long-term context that survives weeks of inactivity | Date ranges |

The raw MEMORY.md entries are never deleted — only organized into a searchable, multi-level summary hierarchy.

## When to invoke

- Automatically nightly at 11pm (cron) — compacts the day's memory entries
- When MEMORY.md grows beyond a configurable threshold (default: 200 entries)
- Before a long-running task — ensures memory is compact and searchable
- When the agent reports "I don't remember" for something that should be in memory

## How to use

```bash
python3 compact.py --compact                      # Run leaf + condensation passes
python3 compact.py --compact --depth 0            # Only leaf summaries (d0)
python3 compact.py --compact --depth 2            # Condense up to d2 arcs
python3 compact.py --status                       # Show DAG stats and health
python3 compact.py --tree                         # Print the summary DAG as a tree
python3 compact.py --search "deployment issue"    # Search across all depths
python3 compact.py --inspect <summary-id>         # Show a summary with its children
python3 compact.py --dissolve <summary-id>        # Reverse a condensation
python3 compact.py --format json                  # Machine-readable output
```

## Procedure

**Step 1 — Run compaction**

```bash
python3 compact.py --compact
```

The compactor:
1. Reads all entries from MEMORY.md
2. Groups entries into chunks (default: 20 entries per leaf)
3. Generates d0 leaf summaries preserving operational detail
4. When leaf count exceeds fanout (default: 5), condenses into d1 summaries
5. Repeats condensation at each depth until DAG is within budget
6. Writes the summary DAG to state

**Step 2 — Search memory across depths**

```bash
python3 compact.py --search "API migration"
```

Searches raw entries and all summary depths. Results ranked by relevance and depth — deeper summaries (d0) are more detailed, shallower (d3+) give the big picture.

**Step 3 — Inspect and repair**

```bash
python3 compact.py --tree             # Visualize the full DAG
python3 compact.py --inspect s-003    # Show summary with lineage
python3 compact.py --dissolve s-007   # Reverse a bad condensation
```

## Depth-aware prompt design

### d0 (Leaf) — Operational detail
Preserves: timestamps, file paths, commands run, error messages, specific values. Drops: conversational filler, repeated attempts, verbose tool output.

### d1 (Condensed) — Session context
Preserves: what changed vs. previous state, decisions made and why, blockers encountered. Drops: per-file details, exact timestamps, intermediate steps.

### d2 (Arc) — Goal-to-outcome arcs
Preserves: goal definition, final outcome, what carries forward, open questions. Drops: session-level detail, individual decisions, specific tools used.

### d3+ (Durable) — Long-term context
Preserves: project identity, architectural decisions, user preferences, recurring patterns. Drops: anything that wouldn't matter after 2 weeks of inactivity.

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `chunk_size` | 20 | Entries per leaf summary |
| `fanout` | 5 | Max children before condensation triggers |
| `max_depth` | 4 | Maximum DAG depth |
| `token_budget` | 8000 | Target token count for assembled context |

## State

DAG structure, summary content, and lineage stored in `~/.openclaw/skill-state/memory-dag-compactor/state.yaml`.

Fields: `last_compact_at`, `dag_nodes`, `dag_edges`, `entry_count`, `compact_history`.

## Notes

- Never modifies or deletes MEMORY.md — the DAG is an overlay
- Each summary includes a `[Expand for details about: ...]` footer listing what was compressed
- Dissolve reverses a condensation, restoring child summaries to the active set
- Inspired by lossless-claw's DAG-based summarization hierarchy and depth-aware prompt system
