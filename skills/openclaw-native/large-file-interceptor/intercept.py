#!/usr/bin/env python3
"""
Large File Interceptor for openclaw-superpowers.

Detects oversized files, generates structural summaries, and stores
compact references to prevent context window blowout.

Usage:
    python3 intercept.py --scan <path>
    python3 intercept.py --scan <path> --threshold 10000
    python3 intercept.py --summarize <file>
    python3 intercept.py --list
    python3 intercept.py --restore <ref-id>
    python3 intercept.py --audit
    python3 intercept.py --status
    python3 intercept.py --format json
"""

import argparse
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "large-file-interceptor" / "state.yaml"
FILE_STORE = OPENCLAW_DIR / "lcm-files"
DEFAULT_THRESHOLD = 25000  # tokens
MAX_HISTORY = 20

# File extensions to analyze
TEXT_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".csv", ".tsv", ".xml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".md", ".txt", ".log", ".conf", ".cfg", ".ini", ".toml",
    ".html", ".css", ".sql", ".sh", ".bash", ".zsh",
    ".env", ".gitignore", ".dockerfile",
}


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"intercepted_files": [], "total_tokens_saved": 0, "scan_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"intercepted_files": [], "total_tokens_saved": 0, "scan_history": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def next_ref_id(state: dict) -> str:
    existing = state.get("intercepted_files") or []
    return f"ref-{len(existing)+1:03d}"


# ── File type detection and structural analysis ──────────────────────────────

def detect_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    type_map = {
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".csv": "CSV", ".tsv": "TSV",
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "JSX", ".tsx": "TSX",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".md": "Markdown", ".txt": "Text",
        ".log": "Log", ".xml": "XML", ".html": "HTML",
        ".css": "CSS", ".sql": "SQL",
        ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    }
    return type_map.get(ext, "Unknown")


def analyze_json(content: str) -> str:
    """Structural summary for JSON files."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return "Invalid JSON — parse error"

    lines = []
    if isinstance(data, dict):
        lines.append(f"Root: object with {len(data)} keys")
        for key, val in list(data.items())[:10]:
            if isinstance(val, list):
                item_type = type(val[0]).__name__ if val else "empty"
                lines.append(f'  "{key}": array of {len(val)} {item_type}s')
            elif isinstance(val, dict):
                lines.append(f'  "{key}": object ({len(val)} keys)')
            else:
                lines.append(f'  "{key}": {type(val).__name__} = {str(val)[:50]}')
        if len(data) > 10:
            lines.append(f"  ... +{len(data)-10} more keys")
    elif isinstance(data, list):
        lines.append(f"Root: array of {len(data)} items")
        if data:
            item = data[0]
            if isinstance(item, dict):
                lines.append(f"  Item keys: {', '.join(list(item.keys())[:8])}")
                sample = json.dumps(item, default=str)[:100]
                lines.append(f"  Sample: {sample}")
    return "\n".join(lines)


def analyze_csv(content: str, delimiter: str = ",") -> str:
    """Structural summary for CSV/TSV files."""
    lines = []
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return "Empty file"

    headers = rows[0] if rows else []
    lines.append(f"Columns ({len(headers)}): {', '.join(headers[:10])}")
    if len(headers) > 10:
        lines.append(f"  ... +{len(headers)-10} more columns")
    lines.append(f"Rows: {len(rows)-1} (excluding header)")

    # Sample values
    if len(rows) > 1:
        sample = rows[1]
        for i, (h, v) in enumerate(zip(headers[:5], sample[:5])):
            lines.append(f"  {h}: {v[:50]}")
    return "\n".join(lines)


def analyze_python(content: str) -> str:
    """Structural summary for Python files."""
    lines = []
    imports = re.findall(r'^(?:import|from)\s+.+', content, re.MULTILINE)
    classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
    functions = re.findall(r'^def\s+(\w+)\(([^)]*)\)', content, re.MULTILINE)

    if imports:
        lines.append(f"Imports ({len(imports)}): {'; '.join(imports[:5])}")
    if classes:
        lines.append(f"Classes: {', '.join(classes)}")
    if functions:
        func_sigs = [f"{name}({args[:30]})" for name, args in functions[:10]]
        lines.append(f"Functions ({len(functions)}): {', '.join(func_sigs)}")
    lines.append(f"Total lines: {content.count(chr(10))+1}")
    return "\n".join(lines)


def analyze_javascript(content: str) -> str:
    """Structural summary for JS/TS files."""
    lines = []
    imports = re.findall(r'^import\s+.+', content, re.MULTILINE)
    exports = re.findall(r'^export\s+(?:default\s+)?(?:class|function|const|let|var|interface|type)\s+(\w+)',
                         content, re.MULTILINE)
    classes = re.findall(r'^(?:export\s+)?class\s+(\w+)', content, re.MULTILINE)
    functions = re.findall(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)', content, re.MULTILINE)

    if imports:
        lines.append(f"Imports ({len(imports)}): {'; '.join(imports[:5])}")
    if exports:
        lines.append(f"Exports: {', '.join(exports[:10])}")
    if classes:
        lines.append(f"Classes: {', '.join(classes)}")
    if functions:
        lines.append(f"Functions: {', '.join(functions[:10])}")
    lines.append(f"Total lines: {content.count(chr(10))+1}")
    return "\n".join(lines)


def analyze_markdown(content: str) -> str:
    """Structural summary for Markdown files."""
    lines = []
    headings = re.findall(r'^(#{1,6})\s+(.+)', content, re.MULTILINE)
    word_count = len(content.split())
    link_count = len(re.findall(r'\[([^\]]+)\]\([^)]+\)', content))

    lines.append(f"Word count: {word_count}")
    if headings:
        lines.append(f"Headings ({len(headings)}):")
        for level, text in headings[:10]:
            lines.append(f"  {'  '*(len(level)-1)}{level} {text}")
    lines.append(f"Links: {link_count}")
    return "\n".join(lines)


def analyze_log(content: str) -> str:
    """Structural summary for log files."""
    lines_list = content.split("\n")
    lines = [f"Total lines: {len(lines_list)}"]

    # Detect time range
    timestamps = re.findall(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', content)
    if timestamps:
        lines.append(f"Time range: {timestamps[0]} → {timestamps[-1]}")

    # Error patterns
    errors = [l for l in lines_list if re.search(r'(?i)error|exception|fatal|panic', l)]
    warns = [l for l in lines_list if re.search(r'(?i)warn', l)]
    lines.append(f"Errors: {len(errors)}, Warnings: {len(warns)}")

    if errors:
        unique_errors = set()
        for e in errors[:20]:
            pattern = re.sub(r'\d+', 'N', e.strip()[:80])
            unique_errors.add(pattern)
        lines.append(f"Unique error patterns: {len(unique_errors)}")
        for p in list(unique_errors)[:3]:
            lines.append(f"  {p}")

    return "\n".join(lines)


def generate_summary(path: Path, content: str) -> str:
    """Generate a structural exploration summary based on file type."""
    file_type = detect_file_type(path)

    analyzers = {
        "JSON": analyze_json,
        "YAML": lambda c: analyze_json(json.dumps(yaml.safe_load(c))) if HAS_YAML else f"YAML file, {len(c)} chars",
        "CSV": lambda c: analyze_csv(c, ","),
        "TSV": lambda c: analyze_csv(c, "\t"),
        "Python": analyze_python,
        "JavaScript": analyze_javascript,
        "TypeScript": analyze_javascript,
        "JSX": analyze_javascript,
        "TSX": analyze_javascript,
        "Markdown": analyze_markdown,
        "Log": analyze_log,
    }

    analyzer = analyzers.get(file_type)
    if analyzer:
        try:
            return analyzer(content)
        except Exception as e:
            return f"Analysis failed: {str(e)[:100]}"
    else:
        return f"File type: {file_type}\nSize: {len(content)} chars\nLines: {content.count(chr(10))+1}"


def generate_reference_card(ref_id: str, path: Path, content: str, summary: str) -> str:
    """Generate a compact reference card for an intercepted file."""
    tokens = estimate_tokens(content)
    file_type = detect_file_type(path)

    card = f"""[FILE REFERENCE: {ref_id}]
Original: {path}
Size: {len(content):,} bytes (~{tokens:,} tokens)
Type: {file_type}

Structure:
{summary}

To retrieve full content: python3 intercept.py --restore {ref_id}"""
    return card


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_scan(state: dict, scan_path: str, threshold: int, fmt: str) -> None:
    path = Path(scan_path).resolve()
    now = datetime.now().isoformat()

    if not path.exists():
        print(f"Error: path '{scan_path}' not found.")
        sys.exit(1)

    # Collect files to scan
    files = []
    if path.is_file():
        files = [path]
    else:
        for ext in TEXT_EXTENSIONS:
            files.extend(path.rglob(f"*{ext}"))

    checked = 0
    intercepted = 0
    tokens_saved = 0

    for fp in files:
        try:
            content = fp.read_text(errors="replace")
        except (PermissionError, OSError):
            continue

        checked += 1
        tokens = estimate_tokens(content)

        if tokens <= threshold:
            continue

        # Intercept this file
        ref_id = next_ref_id(state)
        summary = generate_summary(fp, content)
        summary_tokens = estimate_tokens(summary + ref_id)
        saved = tokens - summary_tokens

        # Store original
        FILE_STORE.mkdir(parents=True, exist_ok=True)
        file_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        stored_name = f"{ref_id}_{file_hash}{fp.suffix}"
        stored_path = FILE_STORE / stored_name
        stored_path.write_text(content)

        record = {
            "ref_id": ref_id,
            "original_path": str(fp),
            "stored_path": str(stored_path),
            "file_type": detect_file_type(fp),
            "original_tokens": tokens,
            "summary_tokens": summary_tokens,
            "tokens_saved": saved,
            "summary": summary,
            "intercepted_at": now,
        }

        files_list = state.get("intercepted_files") or []
        files_list.append(record)
        state["intercepted_files"] = files_list
        intercepted += 1
        tokens_saved += saved

        if fmt != "json":
            card = generate_reference_card(ref_id, fp, content, summary)
            print(f"\n  Intercepted: {fp.name} ({tokens:,} tokens → {summary_tokens:,} tokens)")
            print(f"  Reference card:\n{card}\n")

    state["total_tokens_saved"] = (state.get("total_tokens_saved") or 0) + tokens_saved
    state["last_scan_at"] = now

    history = state.get("scan_history") or []
    history.insert(0, {
        "scanned_at": now, "path_scanned": str(path),
        "files_checked": checked, "files_intercepted": intercepted,
        "tokens_saved": tokens_saved,
    })
    state["scan_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps({"files_checked": checked, "files_intercepted": intercepted,
                          "tokens_saved": tokens_saved}, indent=2))
    else:
        print(f"\nScan Complete — {checked} files checked, {intercepted} intercepted, ~{tokens_saved:,} tokens saved")


def cmd_summarize(path_str: str, fmt: str) -> None:
    path = Path(path_str).resolve()
    if not path.exists():
        print(f"Error: file '{path_str}' not found.")
        sys.exit(1)

    content = path.read_text(errors="replace")
    summary = generate_summary(path, content)
    tokens = estimate_tokens(content)
    summary_tokens = estimate_tokens(summary)

    if fmt == "json":
        print(json.dumps({"file": str(path), "type": detect_file_type(path),
                          "original_tokens": tokens, "summary_tokens": summary_tokens,
                          "summary": summary}, indent=2))
    else:
        print(f"\nStructural Summary: {path.name}")
        print(f"  Type: {detect_file_type(path)} | {tokens:,} tokens → ~{summary_tokens:,} tokens")
        print("-" * 50)
        print(summary)
        print()


def cmd_list(state: dict, fmt: str) -> None:
    files = state.get("intercepted_files") or []
    if fmt == "json":
        print(json.dumps({"intercepted_files": files, "total": len(files)}, indent=2))
    else:
        print(f"\nIntercepted Files — {len(files)} total")
        print("-" * 60)
        for f in files:
            saved = f.get("tokens_saved", 0)
            print(f"  {f['ref_id']}  {f['file_type']:>10}  {f['original_tokens']:>8,} tok → "
                  f"{f['summary_tokens']:>6,} tok  (saved {saved:,})")
            print(f"         {f['original_path']}")
        total = state.get("total_tokens_saved", 0)
        print(f"\n  Total tokens saved: ~{total:,}")
        print()


def cmd_restore(state: dict, ref_id: str) -> None:
    files = state.get("intercepted_files") or []
    target = next((f for f in files if f["ref_id"] == ref_id), None)
    if not target:
        print(f"Error: reference '{ref_id}' not found.")
        sys.exit(1)

    stored = Path(target["stored_path"])
    if stored.exists():
        print(stored.read_text())
    else:
        print(f"Error: stored file not found at {stored}")
        sys.exit(1)


def cmd_audit(state: dict, fmt: str) -> None:
    files = state.get("intercepted_files") or []
    total_original = sum(f.get("original_tokens", 0) for f in files)
    total_summary = sum(f.get("summary_tokens", 0) for f in files)
    total_saved = state.get("total_tokens_saved", 0)

    if fmt == "json":
        print(json.dumps({"files": len(files), "total_original_tokens": total_original,
                          "total_summary_tokens": total_summary, "total_saved": total_saved}, indent=2))
    else:
        print(f"\nContext Budget Audit")
        print("-" * 50)
        print(f"  Intercepted files:     {len(files)}")
        print(f"  Original token cost:   ~{total_original:,}")
        print(f"  Summary token cost:    ~{total_summary:,}")
        print(f"  Total tokens saved:    ~{total_saved:,}")
        if total_original > 0:
            ratio = total_saved / total_original * 100
            print(f"  Compression ratio:     {ratio:.0f}%")
        print()

        # Top consumers
        sorted_files = sorted(files, key=lambda f: f.get("original_tokens", 0), reverse=True)
        if sorted_files:
            print("  Top context consumers:")
            for f in sorted_files[:5]:
                print(f"    {f['ref_id']}  {f['original_tokens']:>8,} tok  {f['original_path']}")
        print()


def cmd_status(state: dict) -> None:
    last = state.get("last_scan_at", "never")
    files = state.get("intercepted_files") or []
    total_saved = state.get("total_tokens_saved", 0)
    print(f"\nLarge File Interceptor — Last scan: {last}")
    print(f"  {len(files)} files intercepted | ~{total_saved:,} tokens saved")
    history = state.get("scan_history") or []
    if history:
        h = history[0]
        print(f"  Last: {h.get('files_checked',0)} checked, "
              f"{h.get('files_intercepted',0)} intercepted at {h.get('path_scanned','?')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Large File Interceptor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", type=str, metavar="PATH", help="Scan a file or directory")
    group.add_argument("--summarize", type=str, metavar="FILE", help="Generate structural summary")
    group.add_argument("--list", action="store_true", help="List all intercepted files")
    group.add_argument("--restore", type=str, metavar="REF_ID", help="Retrieve original file")
    group.add_argument("--audit", action="store_true", help="Show context budget impact")
    group.add_argument("--status", action="store_true", help="Last scan summary")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="Token threshold (default: 25000)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.scan:
        cmd_scan(state, args.scan, args.threshold, args.format)
    elif args.summarize:
        cmd_summarize(args.summarize, args.format)
    elif args.list:
        cmd_list(state, args.format)
    elif args.restore:
        cmd_restore(state, args.restore)
    elif args.audit:
        cmd_audit(state, args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
