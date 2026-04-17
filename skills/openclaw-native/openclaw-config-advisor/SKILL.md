---
name: openclaw-config-advisor
version: "1.0"
category: openclaw-native
description: Diagnoses OpenClaw provider, fallback, channel, MCP, and gateway config issues with read-only scans and stateful summaries.
stateful: true
---

# OpenClaw Config Advisor

Config problems usually look like model failures, missing tools, or broken channels. Use this skill when OpenClaw behaves inconsistently and you need a read-only diagnosis before changing settings.

## When to Invoke

- Provider routing or fallback model behavior is wrong
- A channel cannot connect or stops receiving messages
- MCP tools are missing, stale, or unavailable
- The gateway starts but behaves differently than expected
- You need a current config summary before editing OpenClaw settings

## Checks

| Area | What to inspect |
|---|---|
| Providers | Provider keys, model names, default model hints |
| Fallback | Fallback or backup model settings |
| Channels | Telegram, Discord, Slack, WhatsApp, Signal, or Lark entries |
| MCP | MCP server declarations and command/url hints |
| Gateway | Host, port, log, and process configuration hints |

## How to Use

```bash
python3 advise.py --scan
python3 advise.py --scan --config-dir ~/.openclaw
python3 advise.py --explain fallback
python3 advise.py --status
python3 advise.py --format json
```

## Procedure

1. Run `python3 advise.py --scan --format json`.
2. Review findings by severity: `WARN` first, then `INFO`.
3. Inspect the named config files before editing anything.
4. Apply config changes only after the user confirms the intended routing or channel behavior.
5. Re-run the scan and compare with the prior state summary.

## State

Scan summaries are stored in `~/.openclaw/skill-state/openclaw-config-advisor/state.yaml`.

Fields: `last_scan_at`, `config_dir`, `findings`, `affected_areas`, and `scan_history`.

## Guardrails

- This skill is read-only; it does not modify OpenClaw config.
- Missing config directories are warnings, not crashes.
- Do not print secrets. Report that secret-like values exist without echoing them.
