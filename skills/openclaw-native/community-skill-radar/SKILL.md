---
name: community-skill-radar
version: "1.0"
category: openclaw-native
description: Searches Reddit communities for OpenClaw pain points and feature requests, scores them by signal strength, and writes a prioritized PROPOSALS.md for you to review and act on.
stateful: true
cron: "0 9 */3 * *"
---

# Community Skill Radar

## What it does

Your best skill ideas don't come from guessing — they come from what the community is actually struggling with. Community Skill Radar scans Reddit every 3 days for posts and comments mentioning OpenClaw pain points, feature requests, and skill gaps. It scores them by signal strength (upvotes, comment depth, recurrence) and writes a prioritized `PROPOSALS.md` in the repo root.

You review the proposals. You decide what to build. The radar just makes sure you never miss a signal.

## When to invoke

- Automatically, every 3 days (cron)
- Manually when you want a fresh pulse-check on community needs
- Before planning a new batch of skills

## Subreddits searched

| Subreddit | Why |
|---|---|
| `openclaw` | Primary OpenClaw community |
| `LocalLLaMA` | Local AI users — many run OpenClaw |
| `ClaudeAI` | Claude ecosystem — overlaps with OpenClaw users |
| `MachineLearning` | Broader AI practitioners |
| `AIAgents` | Agent-specific discussions |

Custom subreddits can be configured via `--subreddits`.

## Signal scoring

Each candidate is scored on 5 dimensions:

| Signal | Weight | Source |
|---|---|---|
| Upvotes | 2x | Post/comment score |
| Comment depth | 1.5x | Number of replies — more discussion = stronger signal |
| Recurrence | 3x | Same pain point appearing across multiple posts |
| Keyword density | 1x | Concentration of problem/request keywords |
| Recency | 1.5x | Newer posts score higher (7-day decay) |

## How to use

```bash
python3 radar.py --scan                     # Full scan, write PROPOSALS.md
python3 radar.py --scan --lookback 7        # Scan last 7 days (default: 3)
python3 radar.py --scan --subreddits openclaw,LocalLLaMA
python3 radar.py --scan --min-score 5.0     # Only proposals scoring ≥5.0
python3 radar.py --status                   # Last scan summary from state
python3 radar.py --history                  # Show past scan results
python3 radar.py --format json              # Machine-readable output
```

## Cron wakeup behaviour

Every 3 days at 9am:

1. Fetch recent posts from each configured subreddit via Reddit's public JSON API (no auth required)
2. Filter for posts/comments containing OpenClaw-related keywords
3. Extract pain points and feature request signals
4. Score each candidate
5. Deduplicate against previously seen proposals (stored in state)
6. Write `PROPOSALS.md` to the repo root
7. Print summary to stdout

## PROPOSALS.md format

```markdown
# Skill Proposals — Community Radar

*Last scanned: 2026-03-16 09:00 | 5 subreddits | 14 candidates*

## High Signal (score ≥ 8.0)

### 1. Skill auto-update mechanism (score: 12.4)
- **Source:** r/openclaw — "Anyone else manually pulling skill updates?"
- **Signal:** 47 upvotes, 23 comments, seen 3 times across 2 subreddits
- **Pain point:** No way to update installed skills without manual git pull
- **Potential skill:** `skill-auto-updater` — checks upstream repos for new versions

### 2. Context window usage dashboard (score: 9.1)
- **Source:** r/LocalLLaMA — "My openclaw agent keeps losing context mid-task"
- **Signal:** 31 upvotes, 18 comments
- **Pain point:** No visibility into how much context each skill consumes
- **Potential skill:** `context-usage-dashboard` — real-time token budget display

## Medium Signal (score 4.0–8.0)

...

## Previously Seen (already in state — not re-proposed)

...
```

## Procedure

**Step 1 — Let the cron run (or trigger manually)**

```bash
python3 radar.py --scan
```

**Step 2 — Review PROPOSALS.md**

Open `PROPOSALS.md` in the repo root. High-signal proposals are the ones the community is loudest about.

**Step 3 — Act on proposals you want to build**

For each proposal you decide to build, either:
- Ask your agent to create it: `"Build a skill for <pain point> using create-skill"`
- Open a GitHub issue for the community

**Step 4 — Mark proposals as actioned**

```bash
python3 radar.py --mark-actioned "skill-auto-updater"
```

This moves the proposal to the "actioned" list in state so it won't be re-proposed on future scans.

## State

Scan results, seen proposals, and actioned items stored in `~/.openclaw/skill-state/community-skill-radar/state.yaml`.

Fields: `last_scan_at`, `subreddits`, `proposals` list, `actioned` list, `scan_history`.

## Notes

- Uses Reddit's public JSON API at `reddit.com/<subreddit>/search.json`. No authentication required. Rate-limited to 1 request per 2 seconds to respect Reddit's guidelines.
- Does not post, comment, or interact with Reddit in any way — read-only scanning.
- `PROPOSALS.md` is gitignored by default (local working document). Add to `.gitignore` if not already present.
