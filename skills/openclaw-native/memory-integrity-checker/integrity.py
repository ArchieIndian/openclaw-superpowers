#!/usr/bin/env python3
"""
Memory Integrity Checker for openclaw-superpowers.

Validates memory summary DAGs for structural integrity — orphan nodes,
circular references, token inflation, broken lineage, stale summaries.

Usage:
    python3 integrity.py --check
    python3 integrity.py --check --fix
    python3 integrity.py --check --only ORPHAN_NODE
    python3 integrity.py --repair-plan
    python3 integrity.py --status
    python3 integrity.py --format json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "memory-integrity-checker" / "state.yaml"
DAG_STATE_FILE = OPENCLAW_DIR / "skill-state" / "memory-dag-compactor" / "state.yaml"
MAX_HISTORY = 20
STALE_DAYS = 30


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"findings": [], "check_history": [], "repairs_applied": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"findings": [], "check_history": [], "repairs_applied": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


def load_dag_state() -> dict:
    if not DAG_STATE_FILE.exists():
        return {}
    try:
        text = DAG_STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def save_dag_state(dag: dict) -> None:
    if HAS_YAML:
        with open(DAG_STATE_FILE, "w") as f:
            yaml.dump(dag, f, default_flow_style=False, allow_unicode=True)


# ── Integrity checks ────────────────────────────────────────────────────────

def check_orphan_nodes(nodes: list, edges: list) -> list[dict]:
    """Find nodes with no parent that aren't root nodes (depth > 0)."""
    findings = []
    child_ids = {e["child_id"] for e in edges}
    parent_ids = {e["parent_id"] for e in edges}

    for node in nodes:
        nid = node.get("id", "")
        depth = node.get("depth", 0)
        # Root nodes (not a child of anything) at depth 0 are fine
        if nid not in child_ids and depth > 0:
            findings.append({
                "check": "ORPHAN_NODE",
                "severity": "HIGH",
                "node_id": nid,
                "detail": f"Depth {depth} node has no parent — should be connected to a d{depth-1} parent",
                "auto_fixable": True,
            })
    return findings


def check_circular_refs(nodes: list, edges: list) -> list[dict]:
    """Detect circular parent-child loops using DFS."""
    findings = []
    children_of = {}
    for e in edges:
        children_of.setdefault(e["parent_id"], []).append(e["child_id"])

    def has_cycle(start: str, visited: set, stack: set) -> bool:
        visited.add(start)
        stack.add(start)
        for child in children_of.get(start, []):
            if child in stack:
                return True
            if child not in visited and has_cycle(child, visited, stack):
                return True
        stack.discard(start)
        return False

    visited = set()
    for node in nodes:
        nid = node.get("id", "")
        if nid not in visited:
            if has_cycle(nid, visited, set()):
                findings.append({
                    "check": "CIRCULAR_REF",
                    "severity": "CRITICAL",
                    "node_id": nid,
                    "detail": f"Circular reference detected in DAG involving node {nid}",
                    "auto_fixable": False,
                })
    return findings


def check_token_inflation(nodes: list, edges: list) -> list[dict]:
    """Find summaries with more tokens than their combined children."""
    findings = []
    children_of = {}
    for e in edges:
        children_of.setdefault(e["parent_id"], []).append(e["child_id"])

    node_map = {n.get("id"): n for n in nodes}

    for node in nodes:
        nid = node.get("id", "")
        parent_tokens = node.get("token_count", 0)
        child_ids = children_of.get(nid, [])

        if not child_ids or parent_tokens == 0:
            continue

        children_tokens = sum(
            node_map.get(cid, {}).get("token_count", 0)
            for cid in child_ids
        )

        if children_tokens > 0 and parent_tokens > children_tokens:
            ratio = round(parent_tokens / children_tokens, 1)
            findings.append({
                "check": "TOKEN_INFLATION",
                "severity": "HIGH",
                "node_id": nid,
                "detail": f"Parent ({parent_tokens} tok) > children ({children_tokens} tok) — {ratio}x inflation",
                "auto_fixable": False,
            })
    return findings


def check_broken_lineage(nodes: list, edges: list) -> list[dict]:
    """Find edges referencing non-existent node IDs."""
    findings = []
    node_ids = {n.get("id") for n in nodes}

    for edge in edges:
        if edge["parent_id"] not in node_ids:
            findings.append({
                "check": "BROKEN_LINEAGE",
                "severity": "CRITICAL",
                "node_id": edge["parent_id"],
                "detail": f"Edge references non-existent parent: {edge['parent_id']}",
                "auto_fixable": True,
            })
        if edge["child_id"] not in node_ids:
            findings.append({
                "check": "BROKEN_LINEAGE",
                "severity": "CRITICAL",
                "node_id": edge["child_id"],
                "detail": f"Edge references non-existent child: {edge['child_id']}",
                "auto_fixable": True,
            })
    return findings


def check_stale_active(nodes: list, edges: list) -> list[dict]:
    """Find active nodes older than STALE_DAYS with no children."""
    findings = []
    parent_ids = {e["parent_id"] for e in edges}
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)

    for node in nodes:
        if not node.get("is_active"):
            continue
        nid = node.get("id", "")
        created = node.get("created_at", "")
        if nid in parent_ids:
            continue  # Has children, not stale

        try:
            created_dt = datetime.fromisoformat(created)
            if created_dt < cutoff:
                age_days = (datetime.now() - created_dt).days
                findings.append({
                    "check": "STALE_ACTIVE",
                    "severity": "MEDIUM",
                    "node_id": nid,
                    "detail": f"Active node is {age_days} days old with no children",
                    "auto_fixable": True,
                })
        except (ValueError, TypeError):
            pass
    return findings


def check_empty_nodes(nodes: list) -> list[dict]:
    """Find nodes with empty or whitespace-only content."""
    findings = []
    for node in nodes:
        content = node.get("content", "")
        if len(content.strip()) < 10:
            findings.append({
                "check": "EMPTY_NODE",
                "severity": "HIGH",
                "node_id": node.get("id", "unknown"),
                "detail": f"Node has empty or near-empty content ({len(content.strip())} chars)",
                "auto_fixable": True,
            })
    return findings


def check_duplicate_edges(edges: list) -> list[dict]:
    """Find duplicate parent-child edges."""
    findings = []
    seen = set()
    for edge in edges:
        key = (edge["parent_id"], edge["child_id"])
        if key in seen:
            findings.append({
                "check": "DUPLICATE_EDGE",
                "severity": "LOW",
                "node_id": f"{edge['parent_id']}->{edge['child_id']}",
                "detail": "Duplicate edge in DAG",
                "auto_fixable": True,
            })
        seen.add(key)
    return findings


def check_depth_mismatch(nodes: list, edges: list) -> list[dict]:
    """Check that node depth matches its actual position in the DAG."""
    findings = []
    children_of = {}
    for e in edges:
        children_of.setdefault(e["parent_id"], []).append(e["child_id"])

    node_map = {n.get("id"): n for n in nodes}

    for node in nodes:
        nid = node.get("id", "")
        depth = node.get("depth", 0)
        child_ids = children_of.get(nid, [])

        for cid in child_ids:
            child = node_map.get(cid, {})
            child_depth = child.get("depth", 0)
            if child_depth != depth - 1:
                findings.append({
                    "check": "DEPTH_MISMATCH",
                    "severity": "MEDIUM",
                    "node_id": nid,
                    "detail": f"Parent d{depth} has child d{child_depth} — expected d{depth-1}",
                    "auto_fixable": False,
                })
    return findings


ALL_CHECKS = {
    "ORPHAN_NODE": check_orphan_nodes,
    "CIRCULAR_REF": check_circular_refs,
    "TOKEN_INFLATION": check_token_inflation,
    "BROKEN_LINEAGE": check_broken_lineage,
    "STALE_ACTIVE": check_stale_active,
    "EMPTY_NODE": lambda nodes, edges: check_empty_nodes(nodes),
    "DUPLICATE_EDGE": lambda nodes, edges: check_duplicate_edges(edges),
    "DEPTH_MISMATCH": check_depth_mismatch,
}


# ── Auto-fix ─────────────────────────────────────────────────────────────────

def apply_fix(dag: dict, finding: dict) -> str | None:
    """Apply a safe auto-fix for a finding. Returns action description or None."""
    check = finding["check"]
    nid = finding["node_id"]
    nodes = dag.get("dag_nodes") or []
    edges = dag.get("dag_edges") or []

    if check == "ORPHAN_NODE":
        for n in nodes:
            if n.get("id") == nid:
                n["is_active"] = False
                return f"Deactivated orphan node {nid}"

    elif check == "EMPTY_NODE":
        for n in nodes:
            if n.get("id") == nid:
                n["is_active"] = False
                return f"Deactivated empty node {nid}"

    elif check == "STALE_ACTIVE":
        for n in nodes:
            if n.get("id") == nid:
                n["is_active"] = False
                return f"Deactivated stale node {nid}"

    elif check == "DUPLICATE_EDGE":
        seen = set()
        new_edges = []
        for e in edges:
            key = (e["parent_id"], e["child_id"])
            if key not in seen:
                seen.add(key)
                new_edges.append(e)
        dag["dag_edges"] = new_edges
        return f"Removed duplicate edges"

    elif check == "BROKEN_LINEAGE":
        node_ids = {n.get("id") for n in nodes}
        dag["dag_edges"] = [e for e in edges
                            if e["parent_id"] in node_ids and e["child_id"] in node_ids]
        return f"Removed edges referencing non-existent nodes"

    return None


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_check(state: dict, fix: bool, only: str | None, fmt: str) -> None:
    dag = load_dag_state()
    nodes = dag.get("dag_nodes") or []
    edges = dag.get("dag_edges") or []
    now = datetime.now().isoformat()

    if not nodes:
        print("No DAG nodes found — memory-dag-compactor may not have run yet.")
        return

    all_findings = []
    checks_to_run = {only: ALL_CHECKS[only]} if only and only in ALL_CHECKS else ALL_CHECKS

    for name, check_fn in checks_to_run.items():
        findings = check_fn(nodes, edges)
        all_findings.extend(findings)

    # Count by severity
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in all_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    # Apply fixes if requested
    repairs = []
    if fix:
        fixable = [f for f in all_findings if f.get("auto_fixable") and f["severity"] in ("LOW", "MEDIUM")]
        for finding in fixable:
            action = apply_fix(dag, finding)
            if action:
                repairs.append({
                    "repaired_at": now,
                    "check": finding["check"],
                    "node_id": finding["node_id"],
                    "action": action,
                })
        if repairs:
            save_dag_state(dag)
            existing_repairs = state.get("repairs_applied") or []
            existing_repairs.extend(repairs)
            state["repairs_applied"] = existing_repairs[-50:]

    state["last_check_at"] = now
    state["findings"] = all_findings
    history = state.get("check_history") or []
    history.insert(0, {
        "checked_at": now, "nodes_checked": len(nodes),
        "findings": len(all_findings),
        "critical": counts["CRITICAL"], "high": counts["HIGH"],
        "medium": counts["MEDIUM"], "low": counts["LOW"],
    })
    state["check_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps({"nodes_checked": len(nodes), "findings": all_findings,
                          "counts": counts, "repairs": repairs}, indent=2))
    else:
        print(f"\nMemory Integrity Check — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 55)
        print(f"  Nodes checked: {len(nodes)} | Edges: {len(edges)}")
        print(f"  Findings: {len(all_findings)} "
              f"({counts['CRITICAL']} critical, {counts['HIGH']} high, "
              f"{counts['MEDIUM']} medium, {counts['LOW']} low)")
        print()

        severity_icons = {"CRITICAL": "!!", "HIGH": "!", "MEDIUM": "~", "LOW": "."}
        for f in all_findings:
            icon = severity_icons.get(f["severity"], "?")
            fix_mark = " [auto-fixable]" if f.get("auto_fixable") else ""
            print(f"  {icon} [{f['severity']:>8}] {f['check']}: {f['node_id']}")
            print(f"     {f['detail']}{fix_mark}")

        if repairs:
            print(f"\n  Repairs applied: {len(repairs)}")
            for r in repairs:
                print(f"    + {r['action']}")

        status = "HEALTHY" if not all_findings else "DEGRADED" if not counts["CRITICAL"] else "CRITICAL"
        print(f"\n  Status: {status}")
        print()

    if counts["CRITICAL"] > 0:
        sys.exit(1)


def cmd_repair_plan(state: dict, fmt: str) -> None:
    dag = load_dag_state()
    nodes = dag.get("dag_nodes") or []
    edges = dag.get("dag_edges") or []

    all_findings = []
    for check_fn in ALL_CHECKS.values():
        all_findings.extend(check_fn(nodes, edges))

    fixable = [f for f in all_findings if f.get("auto_fixable")]
    manual = [f for f in all_findings if not f.get("auto_fixable")]

    if fmt == "json":
        print(json.dumps({"auto_fixable": fixable, "manual_required": manual}, indent=2))
    else:
        print(f"\nRepair Plan — {len(all_findings)} findings")
        print("-" * 55)
        if fixable:
            print(f"\n  Auto-fixable ({len(fixable)}):")
            for f in fixable:
                print(f"    {f['check']} on {f['node_id']}: {f['detail']}")
        if manual:
            print(f"\n  Manual review required ({len(manual)}):")
            for f in manual:
                print(f"    [{f['severity']}] {f['check']} on {f['node_id']}: {f['detail']}")
        if not all_findings:
            print("  No issues found — DAG is healthy.")
        print()


def cmd_status(state: dict) -> None:
    last = state.get("last_check_at", "never")
    findings = state.get("findings") or []
    critical = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    print(f"\nMemory Integrity Checker — Last check: {last}")
    print(f"  {len(findings)} findings | {critical} critical")
    repairs = state.get("repairs_applied") or []
    if repairs:
        print(f"  {len(repairs)} repairs applied total")
    print()


def main():
    parser = argparse.ArgumentParser(description="Memory Integrity Checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Run all integrity checks")
    group.add_argument("--repair-plan", action="store_true", help="Generate repair plan")
    group.add_argument("--status", action="store_true", help="Last check summary")
    parser.add_argument("--fix", action="store_true", help="Auto-fix safe issues")
    parser.add_argument("--only", type=str, metavar="CHECK",
                        choices=list(ALL_CHECKS.keys()), help="Run a specific check")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.check:
        cmd_check(state, args.fix, args.only, args.format)
    elif args.repair_plan:
        cmd_repair_plan(state, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
