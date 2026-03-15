---
name: dangerous-action-guard
version: "1.0"
category: openclaw-native
description: Intercepts irreversible or destructive actions and requires explicit user confirmation before proceeding
stateful: true
---

# dangerous-action-guard

Before executing any irreversible or high-impact action, pause and get explicit user confirmation. Log every confirmed and rejected action to an audit trail.

## Dangerous action categories

| Category | Examples |
|---|---|
| **File destruction** | `rm -rf`, `unlink`, delete files, empty trash, wipe directories |
| **Git destructive** | `git push --force`, `git reset --hard`, `git clean -f`, `git branch -D` |
| **External messaging** | Send email, post to Slack/Teams/Discord, publish social post, reply-all |
| **Financial** | Confirm purchase, submit payment, execute trade, cancel subscription |
| **Credentials** | Rotate/delete API keys, modify OAuth apps, change passwords |
| **Infrastructure** | Deploy to production, drop database, terminate server instance |
| **Permission changes** | Share document, change access controls, make resource public |

## Confirmation protocol

When about to execute a dangerous action:

**Step 1 — Pause before the action**
Do not execute the action yet. Write it to `pending_action` in state with a 5-minute expiry.

**Step 2 — Describe to user**
Tell the user:
- What you're about to do (exact command or operation)
- What it will affect (files, people, systems)
- Whether it's reversible and how (if at all)

**Step 3 — Wait for explicit confirmation**
Accept only unambiguous affirmatives: "yes", "go ahead", "confirmed", "do it", "proceed".
Do NOT proceed on: "maybe", "I think so", "sure I guess", or any other hedged response.

**Step 4 — Execute within expiry window**
If confirmed, execute within 5 minutes. If the session lapsed or the user is no longer active, re-confirm.

**Step 5 — Log to audit trail**
Write to state: action, timestamp, user confirmation phrase, outcome (executed / rejected / expired).

## Approval expiry

Approvals expire after **5 minutes**. If you execute a dangerous action more than 5 minutes after receiving confirmation, re-confirm with the user. Stale approvals from prior sessions never carry over.

## Batch operations

For bulk operations (e.g. "delete all temp files"), list the specific items and the count before confirming — never confirm a batch without showing scope. If scope exceeds 10 items, show first 5 and the total count.

## Audit trail

Every action — confirmed or rejected — is logged to state. Use `python3 audit.py --history` to review the full trail. The audit trail is the user's safety net for disputed actions.
