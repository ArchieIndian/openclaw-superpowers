---
name: message-delivery-verifier
version: "1.0"
category: openclaw-native
description: Tracks outbound message delivery across Telegram, Slack, and similar channels — queued, sent, acknowledged, failed, or stale — so users stop missing the final result.
stateful: true
cron: "*/15 * * * *"
---

# Message Delivery Verifier

## What it does

Cron jobs and agents often complete the work but fail on the last step: the message never reaches the user. Message Delivery Verifier maintains a delivery ledger so queued, sent, acknowledged, failed, and stale messages are explicit instead of guessed.

## When to invoke

- Around any workflow that sends a notification, briefing, or deliverable
- When users report "the agent ran but I never got the message"
- As a periodic watchdog for outbound message queues

## Delivery states

- `queued`
- `sent`
- `acknowledged`
- `failed`
- `stale`

## How to use

```bash
python3 verify.py --queue telegram --recipient ops-chat --body "Morning briefing ready"
python3 verify.py --sent telegram --delivery-id msg-001 --receipt telegram:8812
python3 verify.py --ack telegram --delivery-id msg-001
python3 verify.py --fail telegram --delivery-id msg-001 --reason "403 chat not found"
python3 verify.py --stale
python3 verify.py --report
python3 verify.py --format json
```

## Watchdog behaviour

Every 15 minutes:

1. Load queued and sent-but-unacknowledged messages
2. Mark any message older than the stale threshold as `stale`
3. Surface the channel, recipient, and last known receipt
4. Preserve retry recommendations in state

## Difference from cron-execution-prover

`cron-execution-prover` proves that a scheduled workflow ran.

`message-delivery-verifier` proves that the last-mile notification or output actually reached the user.

## State

State file: `~/.openclaw/skill-state/message-delivery-verifier/state.yaml`

Fields: `deliveries`, `stale_deliveries`, `last_report_at`, `report_history`.
