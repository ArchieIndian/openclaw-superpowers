#!/usr/bin/env python3
"""
Memory DAG Compactor for openclaw-superpowers.

Builds hierarchical summary DAGs from MEMORY.md with depth-aware
prompts. Leaf summaries preserve detail; higher depths condense
to durable arcs.

Usage:
    python3 compact.py --compact
    python3 compact.py --compact --depth 2
    python3 compact.py --tree
    python3 compact.py --search "query"
    python3 compact.py --inspect <id>
    python3 compact.py --dissolve <id>
    python3 compact.py --status
    python3 compact.py --format json
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "memory-dag-compactor" / "state.yaml"
MEMORY_FILE = OPENCLAW_DIR / "workspace" / "MEMORY.md"
MAX_HISTORY = 20

# Default config
DEFAULT_CONFIG = {
    "chunk_size": 20,
    "fanout": 5,
    "max_depth": 4,
    "token_budget": 8000,
}

# ── Depth-aware prompt templates ─────────────────────────────────────────────

DEPTH_PROMPTS = {
    0: {
        "name": "Leaf (d0)",
        "instruction": (
            "Summarize these memory entries preserving operational detail.\n"
            "KEEP: timestamps, file paths, commands run, error messages, "
            "specific values, tool outputs, decisions made.\n"
            "DROP: conversational filler, repeated failed attempts (keep final "
            "outcome), verbose intermediate steps.\n"
            "Timeline granularity: hours.\n"
            "End with: [Expand for details about: <comma-separated topics compressed>]"
        ),
    },
    1: {
        "name": "Condensed (d1)",
        "instruction": (
            "Condense these summaries into a session-level overview.\n"
            "KEEP: what changed vs. previous state, decisions made and why, "
            "blockers encountered, tools/APIs used.\n"
            "DROP: per-file details, exact timestamps, intermediate steps, "
            "individual error messages.\n"
            "Timeline granularity: sessions.\n"
            "End with: [Expand for details about: <comma-separated topics compressed>]"
        ),
    },
    2: {
        "name": "Arc (d2)",
        "instruction": (
            "Condense these summaries into goal-to-outcome arcs.\n"
            "KEEP: goal definition, final outcome, what carries forward, "
            "open questions, architectural decisions.\n"
            "DROP: session-level detail, individual decisions, specific "
            "tools used, intermediate blockers.\n"
            "Timeline granularity: days.\n"
            "End with: [Expand for details about: <comma-separated topics compressed>]"
        ),
    },
    3: {
        "name": "Durable (d3+)",
        "instruction": (
            "Condense these summaries into durable long-term context.\n"
            "KEEP: project identity, architectural decisions, user preferences, "
            "recurring patterns, key relationships.\n"
            "DROP: anything that wouldn't matter after 2 weeks of inactivity.\n"
            "Timeline granularity: date ranges.\n"
            "End with: [Expand for details about: <comma-separated topics compressed>]"
        ),
    },
}


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "config": DEFAULT_CONFIG.copy(),
            "dag_nodes": [],
            "dag_edges": [],
            "entry_count": 0,
            "compact_history": [],
        }
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"config": DEFAULT_CONFIG.copy(), "dag_nodes": [], "dag_edges": [],
                "entry_count": 0, "compact_history": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── Memory parsing ───────────────────────────────────────────────────────────

def parse_memory(memory_path: Path) -> list[dict]:
    """Parse MEMORY.md into individual entries."""
    if not memory_path.exists():
        return []
    text = memory_path.read_text()
    entries = []
    current = []
    current_header = ""
    idx = 0

    for line in text.split("\n"):
        # Detect entry boundaries: lines starting with - or ## or timestamps
        is_boundary = (
            line.startswith("- ") or
            line.startswith("## ") or
            re.match(r'^\d{4}-\d{2}-\d{2}', line.strip())
        )
        if is_boundary and current:
            entries.append({
                "id": f"e-{idx:04d}",
                "header": current_header,
                "content": "\n".join(current).strip(),
                "line_count": len(current),
            })
            idx += 1
            current = [line]
            current_header = line.strip()[:80]
        else:
            current.append(line)
            if not current_header and line.strip():
                current_header = line.strip()[:80]

    if current:
        entries.append({
            "id": f"e-{idx:04d}",
            "header": current_header,
            "content": "\n".join(current).strip(),
            "line_count": len(current),
        })
    return entries


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


# ── DAG operations ───────────────────────────────────────────────────────────

def gen_summary_id(depth: int, index: int) -> str:
    return f"s-d{depth}-{index:03d}"


def get_depth_prompt(depth: int) -> dict:
    if depth >= 3:
        return DEPTH_PROMPTS[3]
    return DEPTH_PROMPTS.get(depth, DEPTH_PROMPTS[0])


def generate_leaf_summary(entries: list[dict], depth: int = 0) -> str:
    """Generate a deterministic summary from entries using depth-aware rules."""
    prompt = get_depth_prompt(depth)
    lines = []

    if depth == 0:
        # Leaf: preserve operational detail
        for e in entries:
            content = e["content"]
            # Keep first 3 lines of each entry for detail
            entry_lines = content.split("\n")[:3]
            lines.append(" | ".join(l.strip() for l in entry_lines if l.strip()))
        topics = extract_topics(entries)
        summary = "; ".join(lines[:10])
        if len(lines) > 10:
            summary += f" ... (+{len(lines)-10} more entries)"
        summary += f"\n[Expand for details about: {', '.join(topics[:5])}]"

    elif depth == 1:
        # Condensed: focus on changes and decisions
        for e in entries:
            content = e.get("content", "")
            first_line = content.split("\n")[0].strip()
            lines.append(first_line)
        topics = extract_topics(entries)
        summary = "Session: " + "; ".join(lines[:8])
        if len(lines) > 8:
            summary += f" ... (+{len(lines)-8} more)"
        summary += f"\n[Expand for details about: {', '.join(topics[:5])}]"

    elif depth == 2:
        # Arc: goal → outcome
        all_text = " ".join(e.get("content", "") for e in entries)
        topics = extract_topics(entries)
        summary = f"Arc ({len(entries)} summaries): {all_text[:200].strip()}"
        summary += f"\n[Expand for details about: {', '.join(topics[:5])}]"

    else:
        # Durable: long-term context only
        all_text = " ".join(e.get("content", "") for e in entries)
        topics = extract_topics(entries)
        summary = f"Durable context: {all_text[:150].strip()}"
        summary += f"\n[Expand for details about: {', '.join(topics[:5])}]"

    return summary


def extract_topics(entries: list[dict]) -> list[str]:
    """Extract key topics from a set of entries."""
    # Simple keyword extraction: find capitalized words, paths, and technical terms
    all_text = " ".join(e.get("content", e.get("header", "")) for e in entries)
    words = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)*|[a-z]+(?:[-_][a-z]+)+|/[\w/.-]+', all_text)
    # Deduplicate preserving order
    seen = set()
    topics = []
    for w in words:
        low = w.lower()
        if low not in seen and len(w) > 3:
            seen.add(low)
            topics.append(w)
    return topics[:10]


def compact_entries(state: dict, max_depth: int | None = None) -> dict:
    """Run leaf + condensation passes on MEMORY.md entries."""
    config = state.get("config") or DEFAULT_CONFIG
    chunk_size = config.get("chunk_size", 20)
    fanout = config.get("fanout", 5)
    depth_limit = max_depth if max_depth is not None else config.get("max_depth", 4)

    entries = parse_memory(MEMORY_FILE)
    if not entries:
        return {"entries_processed": 0, "leaves_created": 0,
                "condensations": 0, "max_depth_reached": 0}

    nodes = state.get("dag_nodes") or []
    edges = state.get("dag_edges") or []

    # Track existing entry coverage
    existing_entry_ids = set()
    for node in nodes:
        if node.get("source_type") == "entries":
            sr = node.get("source_range", "")
            for eid in sr.split(","):
                existing_entry_ids.add(eid.strip())

    # Find unprocessed entries
    new_entries = [e for e in entries if e["id"] not in existing_entry_ids]

    if not new_entries:
        return {"entries_processed": 0, "leaves_created": 0,
                "condensations": 0, "max_depth_reached": 0}

    # Step 1: Create leaf summaries (d0)
    leaves_created = 0
    leaf_idx = len([n for n in nodes if n.get("depth") == 0])

    for i in range(0, len(new_entries), chunk_size):
        chunk = new_entries[i:i + chunk_size]
        summary_text = generate_leaf_summary(chunk, depth=0)
        sid = gen_summary_id(0, leaf_idx)

        topics = extract_topics(chunk)
        node = {
            "id": sid,
            "depth": 0,
            "content": summary_text,
            "expand_footer": f"Expand for details about: {', '.join(topics[:5])}",
            "token_count": estimate_tokens(summary_text),
            "created_at": datetime.now().isoformat(),
            "source_type": "entries",
            "source_range": ", ".join(e["id"] for e in chunk),
            "is_active": True,
        }
        nodes.append(node)
        leaf_idx += 1
        leaves_created += 1

    # Step 2: Condensation passes (d1, d2, d3+)
    condensations = 0
    max_depth_reached = 0

    for depth in range(1, depth_limit + 1):
        # Find active nodes at depth-1
        parent_depth = depth - 1
        active_at_depth = [n for n in nodes if n.get("depth") == parent_depth and n.get("is_active")]

        if len(active_at_depth) <= fanout:
            break

        # Condense in groups of fanout
        condense_idx = len([n for n in nodes if n.get("depth") == depth])

        for i in range(0, len(active_at_depth), fanout):
            group = active_at_depth[i:i + fanout]
            if len(group) < 2:
                continue

            summary_text = generate_leaf_summary(group, depth=depth)
            sid = gen_summary_id(depth, condense_idx)

            node = {
                "id": sid,
                "depth": depth,
                "content": summary_text,
                "expand_footer": extract_topics(group),
                "token_count": estimate_tokens(summary_text),
                "created_at": datetime.now().isoformat(),
                "source_type": "summaries",
                "source_range": ", ".join(g["id"] for g in group),
                "is_active": True,
            }
            nodes.append(node)

            # Deactivate children and create edges
            for g in group:
                g["is_active"] = False
                edges.append({"parent_id": sid, "child_id": g["id"]})

            condense_idx += 1
            condensations += 1
            max_depth_reached = max(max_depth_reached, depth)

    state["dag_nodes"] = nodes
    state["dag_edges"] = edges
    state["entry_count"] = len(entries)

    return {
        "entries_processed": len(new_entries),
        "leaves_created": leaves_created,
        "condensations": condensations,
        "max_depth_reached": max_depth_reached,
        "total_nodes": len(nodes),
    }


def dissolve_node(state: dict, node_id: str) -> bool:
    """Reverse a condensation — reactivate children, remove parent."""
    nodes = state.get("dag_nodes") or []
    edges = state.get("dag_edges") or []

    target = None
    for n in nodes:
        if n["id"] == node_id:
            target = n
            break

    if not target:
        return False

    if target.get("depth", 0) == 0:
        print(f"Error: cannot dissolve leaf node {node_id}")
        return False

    # Find and reactivate children
    child_ids = [e["child_id"] for e in edges if e["parent_id"] == node_id]
    for n in nodes:
        if n["id"] in child_ids:
            n["is_active"] = True

    # Remove parent node and edges
    state["dag_nodes"] = [n for n in nodes if n["id"] != node_id]
    state["dag_edges"] = [e for e in edges if e["parent_id"] != node_id]

    return True


# ── Search ───────────────────────────────────────────────────────────────────

def search_dag(state: dict, query: str) -> list[dict]:
    """Search across all DAG nodes and raw entries."""
    results = []
    query_lower = query.lower()
    tokens = set(query_lower.split())

    # Search DAG nodes
    for node in (state.get("dag_nodes") or []):
        content = node.get("content", "").lower()
        if query_lower in content or any(t in content for t in tokens):
            match_count = sum(1 for t in tokens if t in content)
            results.append({
                "type": "summary",
                "id": node["id"],
                "depth": node.get("depth", 0),
                "content": node["content"][:200],
                "relevance": match_count / len(tokens) if tokens else 0,
                "is_active": node.get("is_active", False),
            })

    # Search raw entries
    entries = parse_memory(MEMORY_FILE)
    for entry in entries:
        content = entry.get("content", "").lower()
        if query_lower in content or any(t in content for t in tokens):
            match_count = sum(1 for t in tokens if t in content)
            results.append({
                "type": "entry",
                "id": entry["id"],
                "depth": -1,
                "content": entry["content"][:200],
                "relevance": match_count / len(tokens) if tokens else 0,
                "is_active": True,
            })

    results.sort(key=lambda r: (-r["relevance"], r["depth"]))
    return results


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_compact(state: dict, max_depth: int | None, fmt: str) -> None:
    result = compact_entries(state, max_depth)
    now = datetime.now().isoformat()
    state["last_compact_at"] = now

    history = state.get("compact_history") or []
    history.insert(0, {"compacted_at": now, **result})
    state["compact_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"\nMemory DAG Compaction — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 50)
        print(f"  Entries processed:  {result['entries_processed']}")
        print(f"  Leaves created:     {result['leaves_created']}")
        print(f"  Condensations:      {result['condensations']}")
        print(f"  Max depth reached:  {result['max_depth_reached']}")
        print(f"  Total DAG nodes:    {result.get('total_nodes', len(state.get('dag_nodes', [])))}")
        print()

        if result["entries_processed"] == 0:
            print("  No new entries to compact.")
        else:
            print("  DAG updated successfully.")
        print()


def cmd_tree(state: dict, fmt: str) -> None:
    nodes = state.get("dag_nodes") or []
    edges = state.get("dag_edges") or []

    if fmt == "json":
        print(json.dumps({"nodes": len(nodes), "edges": len(edges),
                          "dag": [{"id": n["id"], "depth": n["depth"],
                                   "active": n.get("is_active", False),
                                   "tokens": n.get("token_count", 0)}
                                  for n in nodes]}, indent=2))
        return

    print(f"\nMemory DAG Tree — {len(nodes)} nodes, {len(edges)} edges")
    print("-" * 50)

    # Build parent map
    children_of = {}
    for e in edges:
        children_of.setdefault(e["parent_id"], []).append(e["child_id"])

    # Find roots (nodes with no parent)
    child_ids = {e["child_id"] for e in edges}
    roots = [n for n in nodes if n["id"] not in child_ids and n.get("is_active")]

    def print_node(node, indent=0):
        prefix = "  " * indent
        active = "+" if node.get("is_active") else "-"
        depth_label = f"d{node.get('depth', 0)}"
        content_preview = node.get("content", "")[:60].replace("\n", " ")
        print(f"{prefix}{active} [{depth_label}] {node['id']}  ({node.get('token_count', 0)} tok)")
        print(f"{prefix}  \"{content_preview}...\"")
        for child_id in children_of.get(node["id"], []):
            child = next((n for n in nodes if n["id"] == child_id), None)
            if child:
                print_node(child, indent + 1)

    if not roots:
        # Show all leaf nodes if no hierarchy yet
        for n in sorted(nodes, key=lambda x: x["id"]):
            print_node(n)
    else:
        for root in sorted(roots, key=lambda x: x["id"]):
            print_node(root)
    print()


def cmd_search(state: dict, query: str, fmt: str) -> None:
    results = search_dag(state, query)

    if fmt == "json":
        print(json.dumps({"query": query, "results": results[:20]}, indent=2))
    else:
        print(f"\nSearch: \"{query}\" — {len(results)} results")
        print("-" * 50)
        for r in results[:15]:
            depth_label = f"d{r['depth']}" if r["depth"] >= 0 else "raw"
            active = "+" if r["is_active"] else "-"
            print(f"  {active} [{depth_label}] {r['id']}  (relevance: {r['relevance']:.1%})")
            print(f"    \"{r['content'][:100]}...\"")
            print()


def cmd_inspect(state: dict, node_id: str, fmt: str) -> None:
    nodes = state.get("dag_nodes") or []
    edges = state.get("dag_edges") or []

    target = next((n for n in nodes if n["id"] == node_id), None)
    if not target:
        print(f"Error: node '{node_id}' not found.")
        sys.exit(1)

    children = [e["child_id"] for e in edges if e["parent_id"] == node_id]
    parents = [e["parent_id"] for e in edges if e["child_id"] == node_id]

    if fmt == "json":
        print(json.dumps({"node": target, "children": children, "parents": parents}, indent=2))
    else:
        print(f"\nInspect: {node_id}")
        print("-" * 50)
        print(f"  Depth:    d{target.get('depth', 0)}")
        print(f"  Active:   {target.get('is_active', False)}")
        print(f"  Tokens:   {target.get('token_count', 0)}")
        print(f"  Created:  {target.get('created_at', '?')}")
        print(f"  Source:   {target.get('source_type', '?')}: {target.get('source_range', '?')}")
        print(f"  Parents:  {', '.join(parents) if parents else 'none (root)'}")
        print(f"  Children: {', '.join(children) if children else 'none (leaf)'}")
        print(f"\n  Content:")
        for line in target.get("content", "").split("\n"):
            print(f"    {line}")
        print()


def cmd_dissolve(state: dict, node_id: str, fmt: str) -> None:
    success = dissolve_node(state, node_id)
    if success:
        save_state(state)
        if fmt == "json":
            print(json.dumps({"dissolved": node_id, "success": True}))
        else:
            print(f"\n  Dissolved {node_id} — children reactivated.")
    else:
        if fmt == "json":
            print(json.dumps({"dissolved": node_id, "success": False}))
        else:
            print(f"\n  Failed to dissolve {node_id}.")
        sys.exit(1)


def cmd_status(state: dict) -> None:
    nodes = state.get("dag_nodes") or []
    last = state.get("last_compact_at", "never")
    entry_count = state.get("entry_count", 0)

    active = [n for n in nodes if n.get("is_active")]
    depth_dist = {}
    for n in nodes:
        d = n.get("depth", 0)
        depth_dist[d] = depth_dist.get(d, 0) + 1

    total_tokens = sum(n.get("token_count", 0) for n in active)

    print(f"\nMemory DAG Compactor — Last compact: {last}")
    print("-" * 50)
    print(f"  Entries tracked:  {entry_count}")
    print(f"  Total DAG nodes:  {len(nodes)}")
    print(f"  Active nodes:     {len(active)}")
    print(f"  Active tokens:    ~{total_tokens}")
    print(f"  Depth distribution:")
    for d in sorted(depth_dist.keys()):
        print(f"    d{d}: {depth_dist[d]} nodes")
    print()

    history = state.get("compact_history") or []
    if history:
        h = history[0]
        print(f"  Last run: {h.get('entries_processed', 0)} entries → "
              f"{h.get('leaves_created', 0)} leaves, "
              f"{h.get('condensations', 0)} condensations")
    print()


def main():
    parser = argparse.ArgumentParser(description="Memory DAG Compactor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--compact", action="store_true", help="Run leaf + condensation passes")
    group.add_argument("--tree", action="store_true", help="Print summary DAG as a tree")
    group.add_argument("--search", type=str, metavar="QUERY", help="Search across all depths")
    group.add_argument("--inspect", type=str, metavar="ID", help="Inspect a summary node")
    group.add_argument("--dissolve", type=str, metavar="ID", help="Reverse a condensation")
    group.add_argument("--status", action="store_true", help="Show DAG stats and health")
    parser.add_argument("--depth", type=int, metavar="N", help="Max depth for compaction")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.compact:
        cmd_compact(state, args.depth, args.format)
    elif args.tree:
        cmd_tree(state, args.format)
    elif args.search:
        cmd_search(state, args.search, args.format)
    elif args.inspect:
        cmd_inspect(state, args.inspect, args.format)
    elif args.dissolve:
        cmd_dissolve(state, args.dissolve, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
