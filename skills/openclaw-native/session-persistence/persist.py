#!/usr/bin/env python3
"""
Session Persistence for openclaw-superpowers.

Imports OpenClaw session transcripts into SQLite with FTS5 full-text search.

Usage:
    python3 persist.py --import
    python3 persist.py --import --source <dir>
    python3 persist.py --search "query"
    python3 persist.py --search "query" --role user
    python3 persist.py --recent --hours 24
    python3 persist.py --conversation <id>
    python3 persist.py --stats
    python3 persist.py --export --format jsonl
    python3 persist.py --status
    python3 persist.py --format json
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "session-persistence" / "state.yaml"
DB_DIR = OPENCLAW_DIR / "lcm-db"
DB_PATH = DB_DIR / "messages.db"
SESSION_DIRS = [
    OPENCLAW_DIR / "sessions",
    OPENCLAW_DIR / "data" / "sessions",
    Path.home() / ".config" / "openclaw" / "sessions",
]
MAX_HISTORY = 20


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"conversation_cursors": {}, "import_history": [],
                "total_messages": 0, "total_conversations": 0}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {"conversation_cursors": {}, "import_history": [],
                "total_messages": 0, "total_conversations": 0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


def estimate_tokens(text: str) -> int:
    return len(text) // 4


# ── Database ─────────────────────────────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            channel TEXT DEFAULT '',
            started_at TEXT,
            last_message_at TEXT,
            message_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT REFERENCES conversations(id),
            seq INTEGER,
            role TEXT,
            content TEXT,
            token_estimate INTEGER,
            created_at TEXT,
            UNIQUE(conversation_id, seq)
        );

        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT,
            conversations_added INTEGER,
            messages_added INTEGER,
            source TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, seq);
        CREATE INDEX IF NOT EXISTS idx_messages_role
            ON messages(role);
        CREATE INDEX IF NOT EXISTS idx_messages_created
            ON messages(created_at);
    """)

    # Try to create FTS5 table (may fail if FTS5 not available)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(content, content='messages', content_rowid='id')
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 not available — will use LIKE fallback

    conn.commit()
    return conn


def has_fts5(conn: sqlite3.Connection) -> bool:
    """Check if FTS5 table exists."""
    try:
        conn.execute("SELECT count(*) FROM messages_fts LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def sync_fts(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 index from messages table."""
    if not has_fts5(conn):
        return
    try:
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        conn.commit()
    except sqlite3.OperationalError:
        pass


# ── JSONL parsing ────────────────────────────────────────────────────────────

def find_session_files(source_dir: Path | None = None) -> list[Path]:
    """Find all JSONL session files."""
    dirs = [source_dir] if source_dir else SESSION_DIRS
    files = []
    for d in dirs:
        if not d.exists():
            continue
        files.extend(d.rglob("*.jsonl"))
        files.extend(d.rglob("*.json"))
    return sorted(set(files))


def parse_jsonl_file(path: Path) -> list[dict]:
    """Parse a JSONL session file into messages."""
    messages = []
    try:
        text = path.read_text(errors="replace")
    except (PermissionError, OSError):
        return []

    for line_num, line in enumerate(text.split("\n")):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Extract message from various formats
        msg = None
        if "message" in data and isinstance(data["message"], dict):
            msg = data["message"]
        elif "role" in data and "content" in data:
            msg = data
        elif "type" in data and data["type"] in ("user", "assistant"):
            msg = data.get("message", data)

        if not msg or "role" not in msg:
            continue

        content = msg.get("content", "")
        if isinstance(content, list):
            # Handle structured content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        if not content or not isinstance(content, str):
            continue

        messages.append({
            "role": msg["role"],
            "content": content,
            "created_at": data.get("timestamp", data.get("created_at",
                          datetime.now().isoformat())),
            "seq": line_num,
        })

    return messages


def conversation_id_from_path(path: Path) -> str:
    """Generate a conversation ID from the file path."""
    return path.stem


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_import(state: dict, source: str | None, fmt: str) -> None:
    conn = init_db()
    now = datetime.now().isoformat()
    source_dir = Path(source) if source else None

    files = find_session_files(source_dir)
    if not files:
        dirs_checked = [source_dir] if source_dir else SESSION_DIRS
        print("No session files found. Searched:")
        for d in dirs_checked:
            print(f"  {d}")
        return

    cursors = state.get("conversation_cursors") or {}
    total_convos_added = 0
    total_msgs_added = 0

    for fpath in files:
        conv_id = conversation_id_from_path(fpath)
        messages = parse_jsonl_file(fpath)
        if not messages:
            continue

        last_seq = cursors.get(conv_id, -1)
        new_messages = [m for m in messages if m["seq"] > last_seq]
        if not new_messages:
            continue

        # Ensure conversation exists
        existing = conn.execute("SELECT id FROM conversations WHERE id=?",
                                (conv_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO conversations (id, channel, started_at, last_message_at, message_count) "
                "VALUES (?, ?, ?, ?, 0)",
                (conv_id, "", new_messages[0]["created_at"], new_messages[-1]["created_at"])
            )
            total_convos_added += 1

        for msg in new_messages:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO messages "
                    "(conversation_id, seq, role, content, token_estimate, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (conv_id, msg["seq"], msg["role"], msg["content"],
                     estimate_tokens(msg["content"]), msg["created_at"])
                )
                total_msgs_added += 1
            except sqlite3.IntegrityError:
                pass

        # Update conversation stats
        conn.execute(
            "UPDATE conversations SET last_message_at=?, message_count=message_count+? WHERE id=?",
            (new_messages[-1]["created_at"], len(new_messages), conv_id)
        )
        cursors[conv_id] = max(m["seq"] for m in new_messages)

    conn.execute(
        "INSERT INTO import_log (imported_at, conversations_added, messages_added, source) "
        "VALUES (?, ?, ?, ?)",
        (now, total_convos_added, total_msgs_added, str(source_dir or "default"))
    )
    conn.commit()
    sync_fts(conn)
    conn.close()

    # Update state
    state["conversation_cursors"] = cursors
    state["last_import_at"] = now
    state["total_messages"] = (state.get("total_messages") or 0) + total_msgs_added
    state["total_conversations"] = (state.get("total_conversations") or 0) + total_convos_added
    state["db_path"] = str(DB_PATH)

    history = state.get("import_history") or []
    history.insert(0, {
        "imported_at": now, "conversations_added": total_convos_added,
        "messages_added": total_msgs_added, "source": str(source_dir or "default"),
    })
    state["import_history"] = history[:MAX_HISTORY]
    save_state(state)

    if fmt == "json":
        print(json.dumps({"files_scanned": len(files), "conversations_added": total_convos_added,
                          "messages_added": total_msgs_added}, indent=2))
    else:
        print(f"\nSession Import — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 50)
        print(f"  Files scanned:        {len(files)}")
        print(f"  Conversations added:  {total_convos_added}")
        print(f"  Messages imported:    {total_msgs_added}")
        print(f"  Database: {DB_PATH}")
        print()


def cmd_search(query: str, role: str | None, fmt: str) -> None:
    if not DB_PATH.exists():
        print("Database not found. Run --import first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    results = []
    if has_fts5(conn):
        # Sanitize FTS5 query
        safe_query = re.sub(r'[^\w\s]', ' ', query)
        sql = """
            SELECT m.conversation_id, m.seq, m.role, m.content, m.created_at,
                   rank
            FROM messages_fts fts
            JOIN messages m ON fts.rowid = m.id
            WHERE messages_fts MATCH ?
        """
        params = [safe_query]
        if role:
            sql += " AND m.role = ?"
            params.append(role)
        sql += " ORDER BY rank LIMIT 20"

        try:
            results = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            results = []

    if not results:
        # LIKE fallback
        sql = "SELECT conversation_id, seq, role, content, created_at FROM messages WHERE content LIKE ?"
        params = [f"%{query}%"]
        if role:
            sql += " AND role = ?"
            params.append(role)
        sql += " ORDER BY created_at DESC LIMIT 20"
        results = conn.execute(sql, params).fetchall()

    conn.close()

    if fmt == "json":
        print(json.dumps({"query": query, "results": [dict(r) for r in results]}, indent=2))
    else:
        print(f"\nSearch: \"{query}\" — {len(results)} results")
        print("-" * 55)
        for r in results:
            content = r["content"][:120].replace("\n", " ")
            ts = (r["created_at"] or "")[:16]
            print(f"  [{r['role']:>9}] {ts}  {r['conversation_id'][:12]}...")
            print(f"    \"{content}...\"")
            print()


def cmd_recent(hours: int, fmt: str) -> None:
    if not DB_PATH.exists():
        print("Database not found. Run --import first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    results = conn.execute(
        "SELECT conversation_id, seq, role, content, created_at FROM messages "
        "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 50",
        (cutoff,)
    ).fetchall()
    conn.close()

    if fmt == "json":
        print(json.dumps({"hours": hours, "messages": [dict(r) for r in results]}, indent=2))
    else:
        print(f"\nRecent Messages (last {hours}h) — {len(results)} messages")
        print("-" * 55)
        for r in results:
            content = r["content"][:100].replace("\n", " ")
            ts = (r["created_at"] or "")[:16]
            print(f"  [{r['role']:>9}] {ts}  \"{content}...\"")
        print()


def cmd_conversation(conv_id: str, fmt: str) -> None:
    if not DB_PATH.exists():
        print("Database not found. Run --import first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    results = conn.execute(
        "SELECT seq, role, content, created_at FROM messages "
        "WHERE conversation_id = ? ORDER BY seq", (conv_id,)
    ).fetchall()
    conn.close()

    if not results:
        # Try partial match
        conn2 = sqlite3.connect(str(DB_PATH))
        conn2.row_factory = sqlite3.Row
        results = conn2.execute(
            "SELECT seq, role, content, created_at FROM messages "
            "WHERE conversation_id LIKE ? ORDER BY seq", (f"%{conv_id}%",)
        ).fetchall()
        conn2.close()

    if fmt == "json":
        print(json.dumps({"conversation": conv_id, "messages": [dict(r) for r in results]}, indent=2))
    else:
        print(f"\nConversation: {conv_id} — {len(results)} messages")
        print("-" * 55)
        for r in results:
            content = r["content"][:200].replace("\n", " ")
            ts = (r["created_at"] or "")[:16]
            print(f"  [{r['seq']:>4}] [{r['role']:>9}] {ts}")
            print(f"    {content}")
            print()


def cmd_stats(fmt: str) -> None:
    if not DB_PATH.exists():
        print("Database not found. Run --import first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    total_msgs = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    total_convos = conn.execute("SELECT count(*) FROM conversations").fetchone()[0]
    roles = conn.execute("SELECT role, count(*) as cnt FROM messages GROUP BY role").fetchall()
    date_range = conn.execute(
        "SELECT min(created_at), max(created_at) FROM messages"
    ).fetchone()
    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    conn.close()

    if fmt == "json":
        print(json.dumps({
            "total_messages": total_msgs, "total_conversations": total_convos,
            "roles": {r[0]: r[1] for r in roles},
            "earliest": date_range[0], "latest": date_range[1],
            "db_size_bytes": db_size,
        }, indent=2))
    else:
        print(f"\nSession Persistence Stats")
        print("-" * 50)
        print(f"  Messages:      {total_msgs:,}")
        print(f"  Conversations: {total_convos}")
        print(f"  Database size: {db_size / 1024:.0f} KB")
        if date_range[0]:
            print(f"  Date range:    {date_range[0][:10]} → {date_range[1][:10]}")
        print(f"\n  By role:")
        for r in roles:
            print(f"    {r[0]:>12}: {r[1]:,}")
        print()


def cmd_export(fmt: str) -> None:
    if not DB_PATH.exists():
        print("Database not found. Run --import first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    messages = conn.execute(
        "SELECT conversation_id, seq, role, content, token_estimate, created_at "
        "FROM messages ORDER BY conversation_id, seq"
    ).fetchall()
    conn.close()

    for m in messages:
        print(json.dumps(dict(m)))


def cmd_status(state: dict) -> None:
    last = state.get("last_import_at", "never")
    total_msgs = state.get("total_messages", 0)
    total_convos = state.get("total_conversations", 0)
    print(f"\nSession Persistence — Last import: {last}")
    print(f"  {total_msgs:,} messages | {total_convos} conversations")
    print(f"  Database: {state.get('db_path', str(DB_PATH))}")
    history = state.get("import_history") or []
    if history:
        h = history[0]
        print(f"  Last: +{h.get('messages_added', 0)} messages, "
              f"+{h.get('conversations_added', 0)} conversations")
    print()


def main():
    parser = argparse.ArgumentParser(description="Session Persistence")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--import", dest="do_import", action="store_true",
                       help="Import new messages from session files")
    group.add_argument("--search", type=str, metavar="QUERY", help="FTS5 full-text search")
    group.add_argument("--recent", action="store_true", help="Recent messages")
    group.add_argument("--conversation", type=str, metavar="ID", help="Dump a conversation")
    group.add_argument("--stats", action="store_true", help="Database statistics")
    group.add_argument("--export", action="store_true", help="Export to JSONL")
    group.add_argument("--status", action="store_true", help="Last import summary")
    parser.add_argument("--source", type=str, metavar="DIR", help="Session files directory")
    parser.add_argument("--role", type=str, help="Filter by role (user/assistant)")
    parser.add_argument("--hours", type=int, default=24, help="Hours for --recent (default: 24)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.do_import:
        cmd_import(state, args.source, args.format)
    elif args.search:
        cmd_search(args.search, args.role, args.format)
    elif args.recent:
        cmd_recent(args.hours, args.format)
    elif args.conversation:
        cmd_conversation(args.conversation, args.format)
    elif args.stats:
        cmd_stats(args.format)
    elif args.export:
        cmd_export(args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
