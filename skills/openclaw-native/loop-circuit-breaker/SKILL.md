---
name: loop-circuit-breaker
version: "1.0"
category: openclaw-native
description: Detects infinite tool-call retry loops from deterministic errors and breaks them before they drain context or budget
stateful: true
---

# loop-circuit-breaker

OpenClaw retries all errors identically — whether transient (rate limit, timeout) or deterministic (missing parameter, type error, invalid path). This skill tracks tool call history per session, identifies repeated identical failures, and halts the loop before it exhausts the context window and API budget.

## Difference from agent-self-recovery

`agent-self-recovery` is a manual, reactive recovery protocol — the user or agent invokes it after noticing the agent is stuck.

`loop-circuit-breaker` is automatic and proactive — it triggers on the 2nd identical failure, before the user even notices.

## Detection algorithm

On every tool call result, the agent should check:

1. Was this tool call a failure (error, exception, or empty result)?
2. Normalise the call signature: `(tool_name, sorted_args_hash, error_type)`
3. Look up this signature in the session's call history in state
4. If the **same signature has failed N times** (default: 2), trigger the circuit breaker

**N=2 rationale:** One retry is reasonable for transient errors. Two identical failures with identical args strongly indicates a deterministic error that retrying cannot resolve.

## Error classification

| Error type | Classification | Max retries |
|---|---|---|
| Rate limit (429) | Transient | 3 |
| Timeout / network | Transient | 3 |
| Missing required parameter | Deterministic | 1 |
| Type error / validation | Deterministic | 1 |
| File not found | Deterministic | 1 |
| Permission denied | Deterministic | 1 |
| Unknown error | Unknown | 2 |

## When the circuit trips

1. **Stop retrying immediately** — do not emit the same call again
2. **Diagnose the root cause** — read the error message carefully
3. **Write `LOOP_DETECTED` to state** with: tool name, args, error, fail count, first/last timestamp
4. **Surface to user**: "I've detected a retry loop on `<tool>(<args>)`. The error is: `<error>`. I've stopped retrying. How would you like me to proceed?"
5. **Offer options**: fix the args, skip this step, or abort the task

## Session scope

Loop detection is per-session. State resets at the start of each new session. Call history older than 2 hours is pruned from state automatically.

## Tuning

To adjust the deterministic retry threshold:
```
python3 check.py --set-threshold 3   # Allow 3 failures before tripping
```
