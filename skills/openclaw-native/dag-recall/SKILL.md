---
name: dag-recall
version: "1.0"
category: openclaw-native
description: Walks the memory DAG to recall detailed context on demand — query, expand, and assemble cited answers from hierarchical summaries without re-reading raw transcripts.
stateful: true
---

# DAG Recall

## What it does

When the agent needs to recall something from past sessions, reading raw transcripts is expensive and often exceeds context limits. DAG Recall walks the hierarchical summary DAG built by memory-dag-compactor — starting from high-level (d2/d3) nodes, expanding into detailed (d0/d1) children — and assembles a focused, cited answer.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s sub-agent recall pattern, where a lightweight agent fetches and expands nodes on demand rather than loading entire conversation histories.

## When to invoke

- When the agent asks "what did we decide about X?" or "how did we implement Y?"
- When context about a past session is needed but the transcript isn't loaded
- When searching MEMORY.md returns only high-level summaries that need expansion
- Before starting work that depends on decisions or patterns from earlier sessions

## How to use

```bash
python3 recall.py --query "how did we handle auth migration"   # Walk DAG + assemble answer
python3 recall.py --query "deploy process" --depth 2           # Limit expansion depth
python3 recall.py --query "API keys" --top 5                   # Return top 5 matching nodes
python3 recall.py --expand s-d1-003                            # Expand a specific node
python3 recall.py --trace s-d0-012                             # Show full ancestor chain
python3 recall.py --recent --hours 48                          # Recall from recent nodes only
python3 recall.py --status                                     # Last recall summary
python3 recall.py --format json                                # Machine-readable output
```

## Recall algorithm

1. **Search** — FTS5 query across all DAG node summaries
2. **Rank** — Score by relevance × recency × depth (deeper = more detailed = higher score for recall)
3. **Expand** — For each top-N match, walk to children (lower depth = more detail)
4. **Assemble** — Combine expanded content into a coherent answer with node citations
5. **Cache** — Store the assembled answer for fast re-retrieval

### Expansion strategy

```
Query: "auth migration"
  ↓
d3 node: "Infrastructure & Auth overhaul Q1" (score: 0.72)
  → expand d2: "Auth migration week of Feb 10" (score: 0.89)
    → expand d1: "Migrated JWT signing from HS256 to RS256" (score: 0.95)
      → expand d0: [raw operational detail — returned as-is]
```

Expansion stops when:
- Target depth reached (default: expand to d0)
- Token budget exhausted (default: 4000 tokens)
- No children exist (leaf node)

## DAG structure expected

Reads from `~/.openclaw/lcm-dag/` (same directory as memory-dag-compactor):

```
~/.openclaw/lcm-dag/
├── index.json          # Node metadata: id, depth, summary, children, created_at
├── nodes/
│   ├── s-d0-001.md     # Leaf node (operational detail)
│   ├── s-d1-001.md     # Condensed summary
│   ├── s-d2-001.md     # Arc summary
│   └── s-d3-001.md     # Durable summary
└── fts.db              # FTS5 index over node summaries
```

## Procedure

**Step 1 — Query the DAG**

```bash
python3 recall.py --query "how did we handle the database migration"
```

Searches the FTS5 index, ranks results, expands top matches, and assembles a cited answer:

```
Recall: "how did we handle the database migration" — 3 sources

  We migrated the database schema using Alembic with a blue-green
  deployment strategy. The key decisions were:

  1. Zero-downtime migration using shadow tables [s-d1-003]
  2. Rollback script tested against staging first [s-d0-012]
  3. Data backfill ran as async job over 2 hours [s-d0-015]

  Sources:
    [s-d1-003] "Database migration — shadow table approach" (Feb 12)
    [s-d0-012] "Alembic rollback script for users table" (Feb 12)
    [s-d0-015] "Async backfill job for legacy records" (Feb 13)
```

**Step 2 — Expand a specific node**

```bash
python3 recall.py --expand s-d1-003
```

Shows the full content of a node and lists its children for further expansion.

**Step 3 — Trace lineage**

```bash
python3 recall.py --trace s-d0-012
```

Shows the full ancestor chain from leaf to root, revealing how detail connects to high-level themes.

## Integration with other skills

- **memory-dag-compactor**: Produces the DAG that this skill reads — must be run first
- **session-persistence**: Alternative data source — recall can fall back to SQLite search when DAG nodes are insufficient
- **context-assembly-scorer**: Recall results feed into context assembly scoring
- **memory-integrity-checker**: Ensures DAG is structurally sound before recall walks it

## State

Recall history and cache stored in `~/.openclaw/skill-state/dag-recall/state.yaml`.

Fields: `last_query`, `last_query_at`, `cache_size`, `total_recalls`, `recall_history`.

## Notes

- Uses Python's built-in `sqlite3` and `json` modules — no external dependencies
- FTS5 used for search when available; falls back to substring matching
- Token budget prevents runaway expansion on large DAGs
- Cache is LRU with configurable max size (default: 50 entries)
- If DAG doesn't exist yet, prints a helpful message pointing to memory-dag-compactor
