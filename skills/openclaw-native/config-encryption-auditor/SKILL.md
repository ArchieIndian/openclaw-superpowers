---
name: config-encryption-auditor
version: "1.0"
category: openclaw-native
description: Scans OpenClaw config directories for plaintext API keys, tokens, and secrets in unencrypted files — flags exposure risks and suggests encryption or environment variable migration.
stateful: true
cron: "0 9 * * 0"
---

# Config Encryption Auditor

## What it does

OpenClaw stores configuration in `~/.openclaw/` — API keys, channel tokens, provider credentials. By default, these are plaintext YAML or JSON files readable by any process on your machine.

OpenLobster solved this with AES-GCM encrypted config files. We can't change OpenClaw's config format, but we can audit it — scanning for exposed secrets, flagging unencrypted credential files, and suggesting migrations to environment variables or encrypted vaults.

## When to invoke

- Automatically, every Sunday at 9am (cron)
- After initial OpenClaw setup
- Before deploying to shared infrastructure
- After any config change that adds new API keys

## Checks performed

| Check | Severity | What it detects |
|---|---|---|
| PLAINTEXT_API_KEY | CRITICAL | API key patterns in config files (sk-, AKIA, ghp_, etc.) |
| PLAINTEXT_TOKEN | HIGH | OAuth tokens, bearer tokens, passwords in config |
| WORLD_READABLE | HIGH | Config files with 644/755 permissions (readable by all users) |
| NO_GITIGNORE | MEDIUM | Config directory not gitignored (risk of committing secrets) |
| ENV_AVAILABLE | INFO | Secret could be migrated to environment variable |

## How to use

```bash
python3 audit.py --scan                    # Full audit
python3 audit.py --scan --critical-only    # CRITICAL findings only
python3 audit.py --fix-permissions         # chmod 600 on config files
python3 audit.py --suggest-env             # Print env var migration guide
python3 audit.py --status                  # Last audit summary
python3 audit.py --format json
```

## Procedure

**Step 1 — Run the audit**

```bash
python3 audit.py --scan
```

**Step 2 — Fix CRITICAL issues first**

For each PLAINTEXT_API_KEY finding, migrate the key to an environment variable:

```bash
# Instead of storing in config.yaml:
#   api_key: sk-abc123...
# Use:
export OPENCLAW_API_KEY="sk-abc123..."
```

**Step 3 — Fix file permissions**

```bash
python3 audit.py --fix-permissions
```

This sets `chmod 600` on all config files (owner read/write only).

**Step 4 — Verify gitignore coverage**

Ensure `~/.openclaw/` or at minimum the config files are in your global `.gitignore`.

## State

Audit results and history stored in `~/.openclaw/skill-state/config-encryption-auditor/state.yaml`.

Fields: `last_audit_at`, `findings`, `files_scanned`, `audit_history`.
