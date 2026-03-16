---
name: large-file-interceptor
version: "1.0"
category: openclaw-native
description: Detects oversized files that would blow the context window, generates structural exploration summaries, and stores compact references — preventing a single paste from consuming the entire budget.
stateful: true
---

# Large File Interceptor

## What it does

A single large file paste can consume 60–80% of the context window, leaving no room for actual work. Large File Interceptor detects oversized files, generates a structural summary (schema, columns, imports, key definitions), stores the original externally, and replaces it with a compact reference card.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s large file interception layer, which automatically extracts files exceeding 25k tokens.

## When to invoke

- Before processing any file the agent reads or receives — check size first
- When context budget is running low and large files may be the cause
- After a paste or file read — retroactively scan for oversized content
- Periodically to audit what's consuming the most context budget

## How to use

```bash
python3 intercept.py --scan <path>                # Scan a file or directory
python3 intercept.py --scan <path> --threshold 10000  # Custom token threshold
python3 intercept.py --summarize <file>           # Generate structural summary for a file
python3 intercept.py --list                       # List all intercepted files
python3 intercept.py --restore <ref-id>           # Retrieve original file content
python3 intercept.py --audit                      # Show context budget impact
python3 intercept.py --status                     # Last scan summary
python3 intercept.py --format json                # Machine-readable output
```

## Structural exploration summaries

The interceptor generates different summaries based on file type:

| File type | Summary includes |
|---|---|
| JSON/YAML | Top-level schema, key types, array lengths, nested depth |
| CSV/TSV | Column names, row count, sample values, data types per column |
| Python/JS/TS | Imports, class definitions, function signatures, export list |
| Markdown | Heading structure, word count per section, link count |
| Log files | Time range, error count, unique error patterns, frequency |
| Binary/Other | File size, MIME type, magic bytes |

## Reference card format

When a file is intercepted, the original is stored in `~/.openclaw/lcm-files/` and replaced with:

```
[FILE REFERENCE: ref-001]
Original: /path/to/large-file.json
Size: 145,230 bytes (~36,307 tokens)
Type: JSON — API response payload

Structure:
  - Root: object with 3 keys
  - "data": array of 1,247 objects
  - "metadata": object (pagination, timestamps)
  - "errors": empty array

Key fields in data[]: id, name, email, created_at, status
Sample: {"id": 1, "name": "...", "status": "active"}

To retrieve full content: python3 intercept.py --restore ref-001
```

## Procedure

**Step 1 — Scan before processing**

```bash
python3 intercept.py --scan /path/to/file.json
```

If the file exceeds the token threshold (default: 25,000 tokens), it generates a structural summary and stores a reference.

**Step 2 — Audit context impact**

```bash
python3 intercept.py --audit
```

Shows all files in the current workspace ranked by token impact, with recommendations for which to intercept.

**Step 3 — Restore when needed**

```bash
python3 intercept.py --restore ref-001
```

Retrieves the original file content from storage for detailed inspection.

## State

Intercepted file registry and reference cards stored in `~/.openclaw/skill-state/large-file-interceptor/state.yaml`. Original files stored in `~/.openclaw/lcm-files/`.

Fields: `last_scan_at`, `intercepted_files`, `total_tokens_saved`, `scan_history`.

## Notes

- Never deletes or modifies original files — intercept creates a copy + reference
- Token threshold is configurable (default: 25,000 ~= 100KB of text)
- Reference cards are typically 200–400 tokens vs. 25,000+ for the original
- Supports recursive directory scanning with `--scan /path/to/dir`
