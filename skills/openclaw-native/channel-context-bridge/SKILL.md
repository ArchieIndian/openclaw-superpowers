---
name: channel-context-bridge
version: "1.0"
category: openclaw-native
description: Writes a resumé card at session end so context survives channel switches — and auto-injects it as a primer at the start of any new session
stateful: true
---

# channel-context-bridge

When a user switches channels (Telegram → Slack, mobile → desktop, personal → work), the new session starts with zero memory of the prior conversation. The user must re-explain context, repeat decisions, and re-establish what's in progress.

This skill writes a compact "resumé card" at session end and injects it automatically as a context primer at the start of any new session — in any channel.

## Difference from task-handoff

`task-handoff` bridges incomplete tasks between **agents** across restarts.
`channel-context-bridge` bridges conversation context for the **same user** switching between channels mid-task.

## End-of-session protocol

At the end of any session containing meaningful work, the agent should:

1. **Write resumé card** to `~/.openclaw/workspace/session-bridge/latest.md`
2. The card contains:
   - **What we were doing**: 1-sentence topic
   - **Key decisions made**: bulleted list, max 5 items
   - **Open questions**: things left unresolved
   - **Next actions**: specific steps to take next
   - **Critical context**: anything the next session needs to know to avoid wrong assumptions
   - Written at: timestamp, source channel

3. **Keep last 7 cards** as `latest.md`, `prev-1.md`, ..., `prev-6.md`

```
python3 bridge.py --write \
  --topic "Refactoring auth module" \
  --decisions "Use JWT; middleware in /lib/auth" \
  --next "Write tests for TokenValidator"
```

## Start-of-session protocol

At the start of any new session:

1. Check for a recent resumé card (< 24 hours old): `python3 bridge.py --check`
2. If found, inject as context primer:
   *"Picking up from [source channel] at [time]: [topic]. Key decisions: [decisions]. Next: [next-actions]."*
3. If card is > 24 hours old: surface it but don't auto-inject — ask user if they want to resume

## Manual resume

The user can always say "pick up where I left off" — the agent then reads the latest card and resumes explicitly.

```
python3 bridge.py --resume    # Print the latest card in human-readable form
python3 bridge.py --history   # Show last 7 cards
```
