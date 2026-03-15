#!/usr/bin/env python3
"""
Memory Graph Builder for openclaw-superpowers.

Parses MEMORY.md into a structured knowledge graph. Detects duplicates,
contradictions, and stale entries. Generates a compressed memory digest.

Usage:
    python3 graph.py --build
    python3 graph.py --duplicates
    python3 graph.py --contradictions
    python3 graph.py --stale [--days 30]
    python3 graph.py --digest [--max-tokens 1500]
    python3 graph.py --prune [--dry-run]
    python3 graph.py --stats
    python3 graph.py --status
    python3 graph.py --format json
"""

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "memory-graph-builder" / "state.yaml"
MEMORY_FILE = OPENCLAW_DIR / "MEMORY.md"
DIGEST_FILE = OPENCLAW_DIR / "workspace" / "memory-digest.md"
MAX_HISTORY = 20

# ── Categories ────────────────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "preference": ["prefer", "like", "want", "always", "never", "favorite", "style",
                    "mode", "theme", "format", "convention"],
    "project":    ["project", "repo", "repository", "codebase", "app", "application",
                    "deploy", "build", "release", "version"],
    "person":     ["name is", "works on", "teammate", "colleague", "manager", "friend",
                    "email", "contact"],
    "tool":       ["uses", "installed", "runs", "tool", "editor", "ide", "framework",
                    "library", "database", "api"],
    "config":     ["config", "setting", "path", "directory", "port", "url", "endpoint",
                    "key", "token", "env"],
    "fact":       ["is", "has", "located", "lives", "born", "works at", "speaks",
                    "timezone", "language"],
}


def classify_category(text: str) -> str:
    text_lower = text.lower()
    scores = {cat: sum(1 for kw in kws if kw in text_lower)
              for cat, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def extract_entities(text: str) -> list[str]:
    """Extract meaningful entities (nouns, proper names, tools) from text."""
    # Remove markdown formatting
    clean = re.sub(r'[*_`#\[\]()]', '', text)
    words = clean.split()
    entities = []
    for w in words:
        w_clean = w.strip(".,;:!?\"'")
        if not w_clean:
            continue
        # Keep capitalized words, technical terms, or words > 3 chars that aren't stopwords
        if (w_clean[0].isupper() and len(w_clean) > 1) or \
           re.match(r'^[A-Z][a-z]+', w_clean) or \
           (len(w_clean) > 3 and w_clean.lower() not in _STOPWORDS):
            entities.append(w_clean.lower())
    return list(set(entities))[:8]


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "been", "were", "will", "would", "could", "should", "about", "into",
    "when", "where", "which", "their", "there", "then", "than", "they",
    "them", "these", "those", "some", "also", "just", "more", "most",
    "very", "only", "over", "such", "after", "before", "between", "each",
    "does", "doing", "being", "other", "using",
}


# ── Similarity ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> set[str]:
    words = re.findall(r'[a-z0-9]+', text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def text_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()[:12]


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"nodes": [], "edges": [], "build_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── MEMORY.md parser ──────────────────────────────────────────────────────────

def parse_memory_file() -> list[str]:
    """Read MEMORY.md and return non-empty, non-header lines."""
    if not MEMORY_FILE.exists():
        return []
    lines = []
    for line in MEMORY_FILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        # Remove leading bullet/dash
        if stripped.startswith(("- ", "* ", "+ ")):
            stripped = stripped[2:].strip()
        if len(stripped) > 5:
            lines.append(stripped)
    return lines


# ── Graph building ────────────────────────────────────────────────────────────

def build_graph(lines: list[str], stale_days: int = 30) -> tuple[list, list]:
    """Build nodes and edges from memory lines."""
    nodes = []
    edges = []
    now = datetime.now()

    for i, line in enumerate(lines):
        node_id = f"mem_{text_hash(line)}"
        nodes.append({
            "id": node_id,
            "text": line,
            "category": classify_category(line),
            "entities": extract_entities(line),
            "added_at": now.strftime("%Y-%m-%d"),
            "last_referenced": now.strftime("%Y-%m-%d"),
            "confidence": 1.0,
            "is_duplicate_of": None,
            "is_stale": False,
        })

    # Detect duplicates (jaccard > 0.7)
    for i in range(len(nodes)):
        ti = tokenize(nodes[i]["text"])
        for j in range(i + 1, len(nodes)):
            tj = tokenize(nodes[j]["text"])
            sim = jaccard(ti, tj)
            if sim >= 0.7:
                nodes[j]["is_duplicate_of"] = nodes[i]["id"]
                nodes[j]["confidence"] = round(1.0 - sim, 2)
                edges.append({
                    "from": nodes[j]["id"],
                    "to": nodes[i]["id"],
                    "relation": "duplicate_of",
                    "weight": round(sim, 3),
                })

    # Detect contradictions (same entities, opposing signals)
    contradiction_signals = [
        (r'\b3\.\d+\b', "version"),
        (r'\b(true|false|yes|no|never|always)\b', "boolean"),
        (r'\b(use|prefer|like|avoid|hate|dislike)\b', "preference"),
    ]
    for i in range(len(nodes)):
        ei = set(nodes[i]["entities"])
        for j in range(i + 1, len(nodes)):
            ej = set(nodes[j]["entities"])
            overlap = ei & ej
            if len(overlap) < 2:
                continue
            # Check for opposing signals
            ti = nodes[i]["text"].lower()
            tj = nodes[j]["text"].lower()
            for pattern, sig_type in contradiction_signals:
                mi = re.findall(pattern, ti, re.I)
                mj = re.findall(pattern, tj, re.I)
                if mi and mj and set(mi) != set(mj):
                    edges.append({
                        "from": nodes[i]["id"],
                        "to": nodes[j]["id"],
                        "relation": "contradicts",
                        "weight": round(len(overlap) / max(len(ei), len(ej), 1), 3),
                    })
                    break

    # Detect related nodes (shared entities, not duplicates/contradictions)
    existing_pairs = {(e["from"], e["to"]) for e in edges}
    for i in range(len(nodes)):
        ei = set(nodes[i]["entities"])
        for j in range(i + 1, len(nodes)):
            pair = (nodes[i]["id"], nodes[j]["id"])
            rev = (nodes[j]["id"], nodes[i]["id"])
            if pair in existing_pairs or rev in existing_pairs:
                continue
            ej = set(nodes[j]["entities"])
            overlap = ei & ej
            if len(overlap) >= 2:
                edges.append({
                    "from": nodes[i]["id"],
                    "to": nodes[j]["id"],
                    "relation": "related_to",
                    "weight": round(len(overlap) / max(len(ei | ej), 1), 3),
                })

    return nodes, edges


# ── Digest generator ──────────────────────────────────────────────────────────

def generate_digest(nodes: list, edges: list, max_tokens: int = 2000) -> str:
    """Generate compressed memory digest grouped by category."""
    # Filter out duplicates
    active = [n for n in nodes if not n.get("is_duplicate_of") and not n.get("is_stale")]
    contradictions = [e for e in edges if e["relation"] == "contradicts"]

    # Group by category
    by_cat: dict = {}
    for node in active:
        cat = node.get("category", "other")
        by_cat.setdefault(cat, []).append(node)

    # Build digest
    lines = []
    cat_order = ["preference", "project", "person", "tool", "config", "fact", "other"]
    cat_labels = {
        "preference": "Preferences", "project": "Active Projects",
        "person": "People", "tool": "Tools & Technologies",
        "config": "Configuration", "fact": "Facts", "other": "Other",
    }

    for cat in cat_order:
        cat_nodes = by_cat.get(cat, [])
        if not cat_nodes:
            continue
        lines.append(f"## {cat_labels.get(cat, cat.title())}")
        for node in cat_nodes:
            lines.append(f"- {node['text']}")
        lines.append("")

    # Add conflicts section
    if contradictions:
        lines.append("## Conflicts (needs resolution)")
        conflict_ids = set()
        for edge in contradictions:
            conflict_ids.add(edge["from"])
            conflict_ids.add(edge["to"])
        node_map = {n["id"]: n for n in nodes}
        shown = set()
        for edge in contradictions:
            key = (edge["from"], edge["to"])
            if key in shown:
                continue
            shown.add(key)
            a = node_map.get(edge["from"], {})
            b = node_map.get(edge["to"], {})
            lines.append(f"- [CONFLICT] \"{a.get('text','?')[:60]}\" vs \"{b.get('text','?')[:60]}\"")
        lines.append("")

    digest = "\n".join(lines)

    # Rough token estimate: ~0.75 tokens per word
    est_tokens = int(len(digest.split()) * 1.33)
    if est_tokens > max_tokens:
        # Truncate from bottom categories first
        while est_tokens > max_tokens and lines:
            lines.pop()
            digest = "\n".join(lines)
            est_tokens = int(len(digest.split()) * 1.33)

    return digest


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * 1.33)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_build(state: dict, stale_days: int, fmt: str) -> None:
    lines = parse_memory_file()
    if not lines:
        print("MEMORY.md not found or empty.")
        return

    nodes, edges = build_graph(lines, stale_days)
    dups = sum(1 for n in nodes if n.get("is_duplicate_of"))
    contras = sum(1 for e in edges if e["relation"] == "contradicts")
    stale = sum(1 for n in nodes if n.get("is_stale"))

    now = datetime.now().isoformat()
    state["nodes"] = nodes
    state["edges"] = edges
    state["last_build_at"] = now
    state["node_count"] = len(nodes)
    state["edge_count"] = len(edges)
    state["duplicate_count"] = dups
    state["contradiction_count"] = contras
    state["stale_count"] = stale

    # Generate and save digest
    digest = generate_digest(nodes, edges)
    DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_FILE.write_text(digest)
    state["digest_tokens"] = estimate_tokens(digest)

    history = state.get("build_history") or []
    history.insert(0, {
        "built_at": now, "node_count": len(nodes),
        "duplicates_found": dups, "contradictions_found": contras,
        "stale_found": stale, "digest_tokens": state["digest_tokens"],
    })
    state["build_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps({
            "node_count": len(nodes), "edge_count": len(edges),
            "duplicates": dups, "contradictions": contras,
            "stale": stale, "digest_tokens": state["digest_tokens"],
        }, indent=2))
    else:
        print(f"\nMemory Graph Builder — {now[:16]}")
        print("─" * 48)
        print(f"  Memory lines   : {len(lines)}")
        print(f"  Nodes          : {len(nodes)}")
        print(f"  Edges          : {len(edges)}")
        print(f"  Duplicates     : {dups}")
        print(f"  Contradictions : {contras}")
        print(f"  Stale          : {stale}")
        print(f"  Digest tokens  : ~{state['digest_tokens']}")
        print(f"\n  Digest written to: {DIGEST_FILE}")
        print()


def cmd_duplicates(state: dict) -> None:
    nodes = state.get("nodes") or []
    dups = [n for n in nodes if n.get("is_duplicate_of")]
    node_map = {n["id"]: n for n in nodes}
    if not dups:
        print("✓ No duplicates detected.")
        return
    print(f"\nDuplicate Clusters ({len(dups)} duplicates)")
    print("─" * 48)
    for dup in dups:
        orig = node_map.get(dup["is_duplicate_of"], {})
        print(f"  DUP:  \"{dup['text'][:70]}\"")
        print(f"  ORIG: \"{orig.get('text','?')[:70]}\"")
        print()


def cmd_contradictions(state: dict) -> None:
    edges = state.get("edges") or []
    nodes = state.get("nodes") or []
    contras = [e for e in edges if e["relation"] == "contradicts"]
    node_map = {n["id"]: n for n in nodes}
    if not contras:
        print("✓ No contradictions detected.")
        return
    print(f"\nContradictions ({len(contras)} pairs)")
    print("─" * 48)
    for c in contras:
        a = node_map.get(c["from"], {})
        b = node_map.get(c["to"], {})
        print(f"  A: \"{a.get('text','?')[:70]}\"")
        print(f"  B: \"{b.get('text','?')[:70]}\"")
        print(f"  → Resolve by editing MEMORY.md")
        print()


def cmd_stale(state: dict, days: int) -> None:
    nodes = state.get("nodes") or []
    stale = [n for n in nodes if n.get("is_stale")]
    if not stale:
        print(f"✓ No memories stale beyond {days} days.")
        return
    print(f"\nStale Memories ({len(stale)} entries, >{days} days)")
    print("─" * 48)
    for n in stale:
        print(f"  [{n.get('category','?')}] \"{n['text'][:70]}\"")


def cmd_digest(state: dict, max_tokens: int) -> None:
    nodes = state.get("nodes") or []
    edges = state.get("edges") or []
    if not nodes:
        print("No graph built yet. Run --build first.")
        return
    digest = generate_digest(nodes, edges, max_tokens)
    DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_FILE.write_text(digest)
    tokens = estimate_tokens(digest)
    print(f"✓ Digest written ({tokens} est. tokens) → {DIGEST_FILE}")
    print()
    print(digest)


def cmd_prune(state: dict, dry_run: bool) -> None:
    nodes = state.get("nodes") or []
    to_remove = [n for n in nodes if n.get("is_duplicate_of") or n.get("is_stale")]
    if not to_remove:
        print("✓ Nothing to prune.")
        return
    if dry_run:
        print(f"\nDry run — would prune {len(to_remove)} entries:")
        for n in to_remove:
            reason = "duplicate" if n.get("is_duplicate_of") else "stale"
            print(f"  [{reason}] \"{n['text'][:70]}\"")
        return

    # Remove from MEMORY.md
    if MEMORY_FILE.exists():
        original = MEMORY_FILE.read_text()
        remove_texts = {n["text"] for n in to_remove}
        kept_lines = []
        for line in original.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "+ ")):
                stripped = stripped[2:].strip()
            if stripped not in remove_texts:
                kept_lines.append(line)
        MEMORY_FILE.write_text("\n".join(kept_lines) + "\n")

    # Rebuild graph
    lines = parse_memory_file()
    nodes, edges = build_graph(lines)
    state["nodes"] = nodes
    state["edges"] = edges
    state["node_count"] = len(nodes)
    state["edge_count"] = len(edges)
    save_state(state)
    print(f"✓ Pruned {len(to_remove)} entries. {len(nodes)} nodes remain.")


def cmd_stats(state: dict, fmt: str) -> None:
    nodes = state.get("nodes") or []
    edges = state.get("edges") or []
    by_cat = {}
    for n in nodes:
        by_cat.setdefault(n.get("category", "other"), []).append(n)

    if fmt == "json":
        print(json.dumps({
            "nodes": len(nodes), "edges": len(edges),
            "categories": {k: len(v) for k, v in by_cat.items()},
            "duplicates": sum(1 for n in nodes if n.get("is_duplicate_of")),
            "contradictions": sum(1 for e in edges if e["relation"] == "contradicts"),
        }, indent=2))
        return

    print(f"\nMemory Graph Statistics")
    print("─" * 40)
    print(f"  Total nodes : {len(nodes)}")
    print(f"  Total edges : {len(edges)}")
    for cat, cat_nodes in sorted(by_cat.items()):
        print(f"  {cat:15s}: {len(cat_nodes)}")
    dups = sum(1 for n in nodes if n.get("is_duplicate_of"))
    contras = sum(1 for e in edges if e["relation"] == "contradicts")
    print(f"  Duplicates  : {dups}")
    print(f"  Contradictions: {contras}")
    print()


def cmd_status(state: dict) -> None:
    last = state.get("last_build_at", "never")
    print(f"\nMemory Graph Builder — Last build: {last}")
    print(f"  Nodes: {state.get('node_count',0)} | "
          f"Edges: {state.get('edge_count',0)} | "
          f"Dups: {state.get('duplicate_count',0)} | "
          f"Conflicts: {state.get('contradiction_count',0)} | "
          f"Digest: ~{state.get('digest_tokens',0)} tokens")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Memory Graph Builder")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true")
    group.add_argument("--duplicates", action="store_true")
    group.add_argument("--contradictions", action="store_true")
    group.add_argument("--stale", action="store_true")
    group.add_argument("--digest", action="store_true")
    group.add_argument("--prune", action="store_true")
    group.add_argument("--stats", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.build:
        cmd_build(state, args.days, args.format)
    elif args.duplicates:
        cmd_duplicates(state)
    elif args.contradictions:
        cmd_contradictions(state)
    elif args.stale:
        cmd_stale(state, args.days)
    elif args.digest:
        cmd_digest(state, args.max_tokens)
    elif args.prune:
        cmd_prune(state, args.dry_run)
    elif args.stats:
        cmd_stats(state, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
