---
name: skill-portability-checker
version: "1.0"
category: core
description: Validates that a skill's companion scripts declare their OS and binary dependencies correctly, and checks whether those dependencies are actually present on the current machine.
---

# Skill Portability Checker

## What it does

Skills with companion scripts (`.py`, `.sh`) can silently fail on machines where their dependencies aren't installed. A skill written on macOS may call `brew`, `pbcopy`, or use `/usr/local/bin` paths that don't exist on Linux. A Python script may `import pandas` on a system without it.

Skill Portability Checker:
1. Scans companion scripts for OS-specific patterns and external binary calls
2. Checks whether those binaries are present on the current system (`PATH` lookup + `which`)
3. Cross-checks against the skill's declared `os_filter:` frontmatter field (if any)
4. Reports portability issues before the skill fails at runtime

## Frontmatter field checked

```yaml
---
name: my-skill
os_filter: [macos]   # optional: ["macos", "linux", "windows"]
---
```

If `os_filter:` is absent the skill is treated as cross-platform. The checker then warns if OS-specific calls are detected without a corresponding `os_filter:`.

## Checks performed

| Check | Description |
|---|---|
| OS_SPECIFIC_CALL | Script calls macOS/Linux/Windows-only binary without `os_filter:` |
| MISSING_BINARY | Required binary not found on current system PATH |
| BREW_ONLY | Script uses `brew` (macOS-only) but `os_filter:` includes non-macOS |
| PYTHON_IMPORT | Script imports a non-stdlib module; checks if importable |
| HARDCODED_PATH | Absolute path that doesn't exist on this machine (`/usr/local`, `C:\`) |

## How to use

```bash
python3 check.py --check                   # Full portability scan
python3 check.py --check --skill my-skill  # Single skill
python3 check.py --fix-hints my-skill      # Print fix suggestions
python3 check.py --format json
```

## Procedure

**Step 1 — Run the scan**

```bash
python3 check.py --check
```

**Step 2 — Triage FAILs first**

- **MISSING_BINARY**: The script calls a binary that isn't installed. Either install it or add a graceful fallback in the script.
- **OS_SPECIFIC_CALL without os_filter**: Add `os_filter: [macos]` (or whichever OS applies) to the frontmatter so users on other platforms know the skill won't work.

**Step 3 — Review WARNs**

- **PYTHON_IMPORT**: Install the missing module or add a `try/except ImportError` with a graceful degradation path (like `HAS_MODULE = False`).
- **HARDCODED_PATH**: Replace with `Path.home()` or environment-variable-based paths.

**Step 4 — Add os_filter when needed**

If a skill genuinely only works on one OS, declare it:

```yaml
os_filter: [macos]
```

This prevents the skill from being shown as broken on other platforms — it simply won't be loaded there.

## Output example

```
Skill Portability Report — linux (Python 3.11)
────────────────────────────────────────────────
32 skills checked | 1 FAIL | 2 WARN

FAIL  obsidian-sync: MISSING_BINARY
      sync.py calls `osascript` — not found on this system
      Fix: add os_filter: [macos] to frontmatter (osascript is macOS-only)

WARN  morning-briefing: PYTHON_IMPORT
      run.py imports `pync` — not importable on this system
      Fix: wrap in try/except ImportError and degrade gracefully
```
