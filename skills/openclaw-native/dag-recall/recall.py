#!/usr/bin/env python3
"""DAG Recall — walk the memory DAG to recall detailed context on demand.

Query, expand, and assemble cited answers from hierarchical summaries.

Usage:
    python3 recall.py --query "auth migration"        # Search + expand + assemble
    python3 recall.py --query "deploy" --depth 2      # Limit expansion depth
    python3 recall.py --query "API" --top 5           # Top 5 matches
    python3 recall.py --expand s-d1-003               # Expand a specific node
    python3 recall.py --trace s-d0-012                # Ancestor chain to root
    python3 recall.py --recent --hours 48             # Recent nodes only
    python3 recall.py --status                        # Last recall summary
    python3 recall.py --format json                   # Machine-readable output
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

OPENCLAW_DIR = Path.home() / ".openclaw"
DAG_DIR = OPENCLAW_DIR / "lcm-dag"
INDEX_PATH = DAG_DIR / "index.json"
NODES_DIR = DAG_DIR / "nodes"
FTS_DB_PATH = DAG_DIR / "fts.db"
STATE_DIR = OPENCLAW_DIR / "skill-state" / "dag-recall"
STATE_PATH = STATE_DIR / "state.yaml"

DEFAULT_TOKEN_BUDGET = 4000
DEFAULT_TOP_N = 3
DEFAULT_MAX_DEPTH = 0  # expand all the way to d0
DEFAULT_CACHE_SIZE = 50
CHARS_PER_TOKEN = 4  # rough estimate


# ── Index loading ────────────────────────────────────────────────────────────

def load_index():
    """Load the DAG index (node metadata)."""
    if not INDEX_PATH.exists():
        return None
    with open(INDEX_PATH) as f:
        return json.load(f)


def load_node_content(node_id):
    """Read the full content of a DAG node file."""
    node_path = NODES_DIR / f"{node_id}.md"
    if not node_path.exists():
        return None
    return node_path.read_text()


def estimate_tokens(text):
    """Rough token estimate."""
    return len(text) // CHARS_PER_TOKEN


# ── FTS5 search ──────────────────────────────────────────────────────────────

def search_fts(query, limit=20):
    """Search DAG node summaries using FTS5."""
    if not FTS_DB_PATH.exists():
        return search_fallback(query, limit)
    try:
        conn = sqlite3.connect(str(FTS_DB_PATH))
        cur = conn.cursor()
        # Check if FTS table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'")
        if not cur.fetchone():
            conn.close()
            return search_fallback(query, limit)
        cur.execute(
            "SELECT node_id, snippet(nodes_fts, 1, '>>>', '<<<', '...', 40), rank "
            "FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        results = [
            {"node_id": row[0], "snippet": row[1], "score": -row[2]}
            for row in cur.fetchall()
        ]
        conn.close()
        return results
    except Exception:
        return search_fallback(query, limit)


def search_fallback(query, limit=20):
    """Fallback: substring search across index summaries."""
    index = load_index()
    if not index or "nodes" not in index:
        return []
    terms = query.lower().split()
    results = []
    for node in index["nodes"]:
        summary = node.get("summary", "").lower()
        score = sum(1 for t in terms if t in summary)
        if score > 0:
            results.append({
                "node_id": node["id"],
                "snippet": node.get("summary", "")[:120],
                "score": score,
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_results(results, index):
    """Re-score results factoring in depth and recency."""
    if not index or "nodes" not in index:
        return results

    node_map = {n["id"]: n for n in index["nodes"]}
    now = datetime.now(timezone.utc)

    for r in results:
        meta = node_map.get(r["node_id"], {})
        depth = meta.get("depth", 0)

        # Deeper nodes (more detail) get bonus for recall
        depth_bonus = max(0, 3 - depth) * 0.3  # d0=0.9, d1=0.6, d2=0.3, d3=0

        # Recency bonus
        recency_bonus = 0
        created = meta.get("created_at")
        if created:
            try:
                ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days_old = (now - ct).days
                recency_bonus = max(0, 1.0 - days_old / 90)  # linear decay over 90 days
            except Exception:
                pass

        r["final_score"] = r["score"] + depth_bonus + recency_bonus
        r["depth"] = depth

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


# ── Expansion ────────────────────────────────────────────────────────────────

def expand_node(node_id, index, target_depth=0, token_budget=DEFAULT_TOKEN_BUDGET):
    """Expand a node by walking to its children, collecting content."""
    if not index or "nodes" not in index:
        return []

    node_map = {n["id"]: n for n in index["nodes"]}
    collected = []
    tokens_used = 0

    def walk(nid, budget_remaining):
        nonlocal tokens_used
        if budget_remaining <= 0:
            return

        meta = node_map.get(nid)
        if not meta:
            return

        content = load_node_content(nid)
        if not content:
            content = meta.get("summary", "")

        t = estimate_tokens(content)
        if t > budget_remaining:
            # Truncate to fit budget
            char_limit = budget_remaining * CHARS_PER_TOKEN
            content = content[:char_limit] + "..."
            t = budget_remaining

        collected.append({
            "node_id": nid,
            "depth": meta.get("depth", 0),
            "content": content,
            "tokens": t,
            "created_at": meta.get("created_at", ""),
        })
        tokens_used += t

        # Expand children if above target depth
        current_depth = meta.get("depth", 0)
        if current_depth > target_depth:
            children = meta.get("children", [])
            for child_id in children:
                if tokens_used >= token_budget:
                    break
                walk(child_id, token_budget - tokens_used)

    walk(node_id, token_budget)
    return collected


# ── Assembly ─────────────────────────────────────────────────────────────────

def assemble_answer(query, expanded_nodes):
    """Assemble expanded node content into a cited answer."""
    if not expanded_nodes:
        return "No relevant information found in the memory DAG."

    lines = []
    sources = []
    for node in expanded_nodes:
        nid = node["node_id"]
        content = node["content"].strip()
        depth = node["depth"]
        created = node.get("created_at", "unknown")[:10]
        depth_label = {0: "detail", 1: "summary", 2: "arc", 3: "durable"}.get(depth, f"d{depth}")

        lines.append(f"  [{nid}] ({depth_label}) {content[:200]}")
        sources.append(f"    [{nid}] \"{content[:60]}...\" ({created})")

    answer = f"Recall: \"{query}\" — {len(expanded_nodes)} sources\n\n"
    answer += "\n".join(lines)
    answer += "\n\n  Sources:\n"
    answer += "\n".join(sources)
    return answer


# ── Trace ────────────────────────────────────────────────────────────────────

def trace_ancestors(node_id, index):
    """Walk from a node up to its ancestors (parents)."""
    if not index or "nodes" not in index:
        return []

    # Build reverse parent map
    parent_map = {}
    for node in index["nodes"]:
        for child_id in node.get("children", []):
            parent_map[child_id] = node["id"]

    chain = []
    current = node_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        node_map = {n["id"]: n for n in index["nodes"]}
        meta = node_map.get(current)
        if not meta:
            break
        content = load_node_content(current)
        chain.append({
            "node_id": current,
            "depth": meta.get("depth", 0),
            "summary": meta.get("summary", ""),
            "content_preview": (content or "")[:200],
            "created_at": meta.get("created_at", ""),
        })
        current = parent_map.get(current)

    return chain


# ── Cache (LRU) ──────────────────────────────────────────────────────────────

class RecallCache:
    """Simple LRU cache for recall results."""

    def __init__(self, max_size=DEFAULT_CACHE_SIZE):
        self.max_size = max_size
        self.cache = OrderedDict()
        self._load()

    def _cache_path(self):
        return STATE_DIR / "cache.json"

    def _load(self):
        p = self._cache_path()
        if p.exists():
            try:
                data = json.loads(p.read_text())
                for k, v in data.items():
                    self.cache[k] = v
            except Exception:
                pass

    def _save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Keep only max_size entries
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
        self._cache_path().write_text(json.dumps(dict(self.cache), indent=2))

    def get(self, query):
        key = query.lower().strip()
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, query, result):
        key = query.lower().strip()
        self.cache[key] = result
        self.cache.move_to_end(key)
        self._save()

    def size(self):
        return len(self.cache)


# ── State management ─────────────────────────────────────────────────────────

def load_state():
    if STATE_PATH.exists():
        import re
        state = {}
        text = STATE_PATH.read_text()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            m = re.match(r'^(\w[\w_]*):\s*(.*)', line)
            if m:
                state[m.group(1)] = m.group(2).strip().strip('"')
        return state
    return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, v in state.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                if isinstance(item, dict):
                    lines.append(f"  - {json.dumps(item)}")
                else:
                    lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: \"{v}\"" if isinstance(v, str) else f"{k}: {v}")
    STATE_PATH.write_text("\n".join(lines) + "\n")


def update_state_after_recall(query, sources_used, tokens_assembled, cache_hit):
    state = load_state()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    state["last_query"] = query
    state["last_query_at"] = now
    total = int(state.get("total_recalls", 0)) + 1
    state["total_recalls"] = str(total)
    cache = RecallCache()
    state["cache_size"] = str(cache.size())
    save_state(state)


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_query(args):
    """Search DAG, expand matches, assemble cited answer."""
    index = load_index()
    if index is None:
        print("DAG index not found at", INDEX_PATH)
        print("Run memory-dag-compactor first:  python3 compact.py --compact")
        return 1

    cache = RecallCache()

    # Check cache
    if not args.no_cache:
        cached = cache.get(args.query)
        if cached:
            print(cached["answer"])
            update_state_after_recall(args.query, cached["sources"], cached["tokens"], True)
            return 0

    # Search
    results = search_fts(args.query, limit=args.top * 3)
    if not results:
        print(f"No results found for: \"{args.query}\"")
        return 0

    # Score
    results = score_results(results, index)
    top_results = results[:args.top]

    # Expand
    all_expanded = []
    budget = args.token_budget
    for r in top_results:
        expanded = expand_node(
            r["node_id"], index,
            target_depth=args.depth,
            token_budget=budget,
        )
        for e in expanded:
            budget -= e["tokens"]
        all_expanded.extend(expanded)
        if budget <= 0:
            break

    # Deduplicate
    seen = set()
    unique = []
    for e in all_expanded:
        if e["node_id"] not in seen:
            seen.add(e["node_id"])
            unique.append(e)

    # Assemble
    answer = assemble_answer(args.query, unique)

    if args.format == "json":
        out = {
            "query": args.query,
            "sources": len(unique),
            "tokens_assembled": sum(e["tokens"] for e in unique),
            "nodes": unique,
        }
        print(json.dumps(out, indent=2))
    else:
        print(answer)

    # Cache + state
    total_tokens = sum(e["tokens"] for e in unique)
    cache.put(args.query, {"answer": answer, "sources": len(unique), "tokens": total_tokens})
    update_state_after_recall(args.query, len(unique), total_tokens, False)
    return 0


def cmd_expand(args):
    """Expand a specific node, showing content and children."""
    index = load_index()
    if index is None:
        print("DAG index not found. Run memory-dag-compactor first.")
        return 1

    node_map = {n["id"]: n for n in index.get("nodes", [])}
    meta = node_map.get(args.expand)
    if not meta:
        print(f"Node not found: {args.expand}")
        return 1

    content = load_node_content(args.expand)
    children = meta.get("children", [])
    depth = meta.get("depth", 0)

    if args.format == "json":
        print(json.dumps({
            "node_id": args.expand,
            "depth": depth,
            "summary": meta.get("summary", ""),
            "content": content,
            "children": children,
            "created_at": meta.get("created_at", ""),
        }, indent=2))
    else:
        depth_label = {0: "detail", 1: "summary", 2: "arc", 3: "durable"}.get(depth, f"d{depth}")
        print(f"Node: {args.expand}  (depth {depth} — {depth_label})")
        print(f"Created: {meta.get('created_at', 'unknown')}")
        print(f"Summary: {meta.get('summary', 'n/a')}")
        print(f"Children: {len(children)}")
        if children:
            for c in children:
                cmeta = node_map.get(c, {})
                print(f"  → {c} ({cmeta.get('summary', '')[:60]})")
        print()
        print("Content:")
        print(content or "(empty)")
    return 0


def cmd_trace(args):
    """Show full ancestor chain from node to root."""
    index = load_index()
    if index is None:
        print("DAG index not found. Run memory-dag-compactor first.")
        return 1

    chain = trace_ancestors(args.trace, index)
    if not chain:
        print(f"Node not found: {args.trace}")
        return 1

    if args.format == "json":
        print(json.dumps(chain, indent=2))
    else:
        print(f"Trace: {args.trace} → root ({len(chain)} nodes)")
        print()
        for i, node in enumerate(chain):
            indent = "  " * i
            depth_label = {0: "detail", 1: "summary", 2: "arc", 3: "durable"}.get(
                node["depth"], f"d{node['depth']}"
            )
            print(f"{indent}{'└── ' if i > 0 else ''}{node['node_id']} (d{node['depth']} — {depth_label})")
            print(f"{indent}    {node['summary'][:80]}")
            if node["created_at"]:
                print(f"{indent}    Created: {node['created_at'][:10]}")
    return 0


def cmd_recent(args):
    """Show nodes created within the specified time window."""
    index = load_index()
    if index is None:
        print("DAG index not found. Run memory-dag-compactor first.")
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    recent = []
    for node in index.get("nodes", []):
        created = node.get("created_at")
        if created:
            try:
                ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if ct >= cutoff:
                    recent.append(node)
            except Exception:
                pass

    recent.sort(key=lambda n: n.get("created_at", ""), reverse=True)

    if args.format == "json":
        print(json.dumps(recent, indent=2))
    else:
        print(f"Recent nodes (last {args.hours}h): {len(recent)}")
        print()
        for node in recent:
            depth_label = {0: "detail", 1: "summary", 2: "arc", 3: "durable"}.get(
                node.get("depth", 0), "?"
            )
            print(f"  {node['id']}  d{node.get('depth', '?')} ({depth_label})  {node.get('created_at', '')[:16]}")
            print(f"    {node.get('summary', '')[:80]}")
    return 0


def cmd_status(args):
    """Print last recall summary."""
    state = load_state()
    cache = RecallCache()

    if args.format == "json":
        state["cache_size"] = cache.size()
        print(json.dumps(state, indent=2))
    else:
        print("DAG Recall Status")
        print("─" * 50)
        print(f"  Last query:      {state.get('last_query', 'none')}")
        print(f"  Last query at:   {state.get('last_query_at', 'never')}")
        print(f"  Total recalls:   {state.get('total_recalls', 0)}")
        print(f"  Cache size:      {cache.size()} / {DEFAULT_CACHE_SIZE}")
        # Check if DAG exists
        if INDEX_PATH.exists():
            index = load_index()
            n = len(index.get("nodes", [])) if index else 0
            print(f"  DAG nodes:       {n}")
        else:
            print(f"  DAG:             not found ({DAG_DIR})")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DAG Recall — walk the memory DAG to recall context")
    parser.add_argument("--query", type=str, help="Search query to recall information about")
    parser.add_argument("--expand", type=str, help="Expand a specific node by ID")
    parser.add_argument("--trace", type=str, help="Trace ancestor chain for a node")
    parser.add_argument("--recent", action="store_true", help="Show recent nodes")
    parser.add_argument("--status", action="store_true", help="Show recall status")
    parser.add_argument("--depth", type=int, default=DEFAULT_MAX_DEPTH,
                        help=f"Target expansion depth (default: {DEFAULT_MAX_DEPTH} = expand to leaf)")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                        help=f"Number of top results to expand (default: {DEFAULT_TOP_N})")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET,
                        help=f"Max tokens to assemble (default: {DEFAULT_TOKEN_BUDGET})")
    parser.add_argument("--hours", type=int, default=24, help="Hours window for --recent")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache lookup")
    parser.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args()

    if args.query:
        return cmd_query(args)
    elif args.expand:
        return cmd_expand(args)
    elif args.trace:
        return cmd_trace(args)
    elif args.recent:
        return cmd_recent(args)
    elif args.status:
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
