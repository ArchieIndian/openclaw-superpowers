---
name: session-persistence
version: "1.0"
category: openclaw-native
description: Imports OpenClaw session transcripts into a local SQLite database with FTS5 full-text search — the agent never loses a message, even after context compaction or session rollover.
stateful: true
cron: "*/15 * * * *"
---

# Session Persistence

## What it does

OpenClaw stores session data in JSONL files that are difficult to search and easy to lose track of. Session Persistence imports every message into a local SQLite database with full-text search, making the agent's entire history queryable — across all sessions, all channels, all time.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s SQLite message persistence layer, which stores every message with sequence numbers, token counts, and structured message parts.

## When to invoke

- Automatically every 15 minutes (cron) — incremental import of new messages
- When the agent needs to search past conversations — use `--search`
- After a crash or session rollover — verify all messages are persisted
- For analytics — message counts, session timelines, activity patterns

## How to use

```bash
python3 persist.py --import                       # Import new messages from session files
python3 persist.py --import --source <dir>        # Import from a specific directory
python3 persist.py --search "auth migration"      # FTS5 full-text search
python3 persist.py --search "deploy" --role user  # Search only user messages
python3 persist.py --recent --hours 24            # Messages from the last 24 hours
python3 persist.py --conversation <id>            # Dump a full conversation
python3 persist.py --stats                        # Database statistics
python3 persist.py --export --format jsonl        # Export back to JSONL
python3 persist.py --status                       # Last import summary
python3 persist.py --format json                  # Machine-readable output
```

## Database schema

Stored at `~/.openclaw/lcm-db/messages.db`:

```sql
conversations   — id, channel, started_at, last_message_at, message_count
messages        — id, conversation_id, seq, role, content, token_estimate, created_at
messages_fts    — FTS5 virtual table over messages.content for fast search
import_log      — id, imported_at, conversations_added, messages_added, source
```

## Cron wakeup behaviour

Every 15 minutes:

1. Scan session directory for JSONL files
2. For each file, check `last_imported_seq` to skip already-imported messages
3. Parse new messages and insert into SQLite
4. Update FTS5 index
5. Update import log and state

## Procedure

**Step 1 — Initial import**

```bash
python3 persist.py --import
```

First run imports all existing session files. Subsequent runs are incremental — only new messages since last import.

**Step 2 — Search your history**

```bash
python3 persist.py --search "how did we handle the database migration"
```

FTS5 provides ranked results across all sessions and time periods. Results include conversation ID, timestamp, role, and content snippet.

**Step 3 — Analyze patterns**

```bash
python3 persist.py --stats
```

Shows total messages, conversations, date ranges, messages per role, and activity timeline.

## Integration with other skills

- **memory-dag-compactor**: Can use SQLite messages as source data instead of MEMORY.md, bringing architecture closer to lossless-claw
- **dag-recall**: Search results feed into DAG expansion for detailed recall
- **context-assembly-scorer**: Uses message database to measure true coverage

## State

Import tracking and database stats stored in `~/.openclaw/skill-state/session-persistence/state.yaml`.
Database stored at `~/.openclaw/lcm-db/messages.db`.

Fields: `last_import_at`, `db_path`, `total_messages`, `total_conversations`, `import_history`.

## Notes

- Uses Python's built-in `sqlite3` module — no external dependencies
- FTS5 used when available; falls back to LIKE queries otherwise
- Idempotent: safe to re-run; tracks per-conversation sequence numbers
- Import lag: up to 15 minutes behind real-time (cron interval)
- Database is local-only — never committed to the repo
