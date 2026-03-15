---
name: memory-graph-builder
version: "1.0"
category: openclaw-native
description: Parses OpenClaw's flat MEMORY.md into a structured knowledge graph — detects duplicates, contradictions, and stale entries, then builds a compressed memory digest optimized for system prompt injection.
stateful: true
cron: "0 22 * * *"
---

# Memory Graph Builder

## What it does

OpenClaw stores agent memory in a flat `MEMORY.md` file — one line per fact, no structure, no relationships. This works until your agent has 200+ memories and half of them are duplicates, three contradict each other, and the whole file costs 4,000 tokens every session.

Memory Graph Builder treats MEMORY.md as a raw data source and builds a structured knowledge graph on top of it. Each memory becomes a node with typed relationships to other nodes. The graph enables:

- **Duplicate detection** — "User prefers dark mode" and "User likes dark theme" are the same fact
- **Contradiction detection** — "User uses Python 3.8" vs "User uses Python 3.12"
- **Staleness detection** — Facts older than a configurable threshold that haven't been referenced
- **Memory digest** — A compressed, relationship-aware summary that replaces raw MEMORY.md in the system prompt, saving 30-60% tokens

Inspired by OpenLobster's Neo4j-backed graph memory system, adapted to work on top of OpenClaw's existing MEMORY.md without requiring a database.

## When to invoke

- Automatically, nightly at 10pm (cron)
- After bulk memory additions (e.g., after project-onboarding)
- When the agent's context initialisation feels slow (memory bloat)
- Manually to audit memory quality

## Graph structure

Each memory line becomes a node:

```yaml
nodes:
  - id: "mem_001"
    text: "User prefers Python for backend work"
    category: preference    # preference | fact | project | person | tool | config
    entities: ["user", "python", "backend"]
    added_at: "2026-03-01"
    last_referenced: "2026-03-15"
    confidence: 0.9
edges:
  - from: "mem_001"
    to: "mem_014"
    relation: related_to    # related_to | contradicts | supersedes | depends_on
```

## How to use

```bash
python3 graph.py --build                    # Parse MEMORY.md, build graph
python3 graph.py --duplicates               # Show duplicate clusters
python3 graph.py --contradictions           # Show contradicting pairs
python3 graph.py --stale --days 30          # Show memories not referenced in 30 days
python3 graph.py --digest                   # Generate compressed memory digest
python3 graph.py --digest --max-tokens 1500 # Digest with token budget
python3 graph.py --prune --dry-run          # Show what would be removed
python3 graph.py --prune                    # Remove duplicates + stale entries
python3 graph.py --stats                    # Graph statistics
python3 graph.py --status                   # Last build summary
python3 graph.py --format json
```

## Cron wakeup behaviour

Nightly at 10pm:

1. Read MEMORY.md
2. Rebuild graph (incremental — only re-processes new/changed lines)
3. Detect duplicates and contradictions
4. Flag stale entries (>30 days unreferenced by default)
5. Generate fresh memory digest
6. Write digest to `~/.openclaw/workspace/memory-digest.md`
7. Log summary to state

## Memory digest

The digest is a compressed representation of the knowledge graph optimized for LLM consumption. Instead of dumping every raw line, it:

- Groups related memories by category
- Merges duplicate facts into single entries
- Marks contradictions with `[CONFLICT]` so the agent can resolve them
- Omits stale entries below a confidence threshold
- Respects a configurable max-token budget

Example digest output:

```markdown
## Preferences
- Prefers Python for backend, TypeScript for frontend
- Dark mode everywhere; compact UI layouts
- Commit messages: imperative mood, max 72 chars

## Active Projects
- openclaw-superpowers: skill library, 40 skills, MIT license
- personal-site: Next.js 14, deployed on Vercel

## People
- Alice (teammate): works on auth, prefers Go

## Conflicts (needs resolution)
- [CONFLICT] Python version: "3.8" vs "3.12" — ask user to clarify
```

## Procedure

**Step 1 — Build the graph**

```bash
python3 graph.py --build
```

**Step 2 — Review duplicates and contradictions**

```bash
python3 graph.py --duplicates
python3 graph.py --contradictions
```

Fix contradictions by editing MEMORY.md directly or asking the agent to clarify.

**Step 3 — Prune stale entries**

```bash
python3 graph.py --prune --dry-run
python3 graph.py --prune
```

**Step 4 — Generate and use the digest**

```bash
python3 graph.py --digest --max-tokens 1500
```

Point OpenClaw's memory injection at `~/.openclaw/workspace/memory-digest.md` instead of raw MEMORY.md.

## State

Graph structure, digest cache, and audit history stored in `~/.openclaw/skill-state/memory-graph-builder/state.yaml`.

Fields: `last_build_at`, `node_count`, `edge_count`, `duplicate_count`, `contradiction_count`, `stale_count`, `digest_tokens`, `build_history`.
