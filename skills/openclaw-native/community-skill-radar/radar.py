#!/usr/bin/env python3
"""
Community Skill Radar for openclaw-superpowers.

Scans Reddit communities for OpenClaw pain points and feature requests.
Scores candidates by signal strength and writes a prioritized PROPOSALS.md.

Usage:
    python3 radar.py --scan                     # Full scan, write PROPOSALS.md
    python3 radar.py --scan --lookback 7        # Scan last 7 days
    python3 radar.py --scan --subreddits openclaw,LocalLLaMA
    python3 radar.py --scan --min-score 5.0
    python3 radar.py --mark-actioned <id>       # Mark proposal as actioned
    python3 radar.py --status                   # Last scan summary
    python3 radar.py --history                  # Past scan results
    python3 radar.py --format json
"""

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "community-skill-radar" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
PROPOSALS_FILE = SUPERPOWERS_DIR / "PROPOSALS.md"

DEFAULT_SUBREDDITS = ["openclaw", "LocalLLaMA", "ClaudeAI", "MachineLearning", "AIAgents"]
DEFAULT_LOOKBACK_DAYS = 3
RATE_LIMIT_SECONDS = 2.0
MAX_POSTS_PER_SUB = 50
MAX_HISTORY = 20
USER_AGENT = "openclaw-superpowers:community-skill-radar:v1.0 (by /u/openclaw-bot)"

# ── Keywords ──────────────────────────────────────────────────────────────────

# Keywords that signal an OpenClaw-relevant post
OPENCLAW_KEYWORDS = [
    "openclaw", "open claw", "open-claw",
    "skill", "skills", "superpowers",
    "agent", "ai agent", "ai assistant",
    "cron", "scheduled task",
]

# Keywords that signal a pain point or feature request
SIGNAL_KEYWORDS = [
    "wish", "want", "need", "missing", "broken", "frustrat",
    "bug", "issue", "problem", "annoying", "doesn't work",
    "feature request", "would be nice", "someone should",
    "why can't", "how do i", "is there a way",
    "pain point", "struggle", "stuck", "help",
    "workaround", "hack", "janky", "ugly",
    "silent", "silently", "no error", "no warning",
    "expensive", "cost", "budget", "bill",
    "context window", "context limit", "overflow",
    "memory", "forget", "lost context",
]

# Keywords that suggest a potential skill category
SKILL_CATEGORY_KEYWORDS = {
    "security":    ["injection", "malicious", "credential", "secret", "vulnerability", "attack"],
    "cost":        ["expensive", "cost", "budget", "spend", "bill", "token", "usage", "price"],
    "reliability": ["crash", "loop", "stuck", "hang", "timeout", "retry", "fail", "broken"],
    "context":     ["context", "memory", "forget", "window", "overflow", "limit", "compaction"],
    "workflow":    ["workflow", "chain", "pipeline", "orchestrat", "automat", "schedule", "cron"],
    "integration": ["install", "load", "config", "setup", "compati", "version", "portab"],
    "ux":          ["confusing", "unclear", "verbose", "noisy", "silent", "dashboard", "status"],
}


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"proposals": [], "actioned": [], "scan_history": []}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── Reddit fetcher ────────────────────────────────────────────────────────────

def fetch_subreddit(subreddit: str, lookback_days: int) -> list[dict]:
    """Fetch recent posts from a subreddit via Reddit's public JSON API."""
    url = (f"https://www.reddit.com/r/{subreddit}/new.json"
           f"?limit={MAX_POSTS_PER_SUB}&t=week")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    posts = []

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        cutoff = datetime.now() - timedelta(days=lookback_days)

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            created = datetime.fromtimestamp(post.get("created_utc", 0))
            if created < cutoff:
                continue

            posts.append({
                "subreddit": subreddit,
                "post_id": post.get("id", ""),
                "title": post.get("title", ""),
                "selftext": post.get("selftext", "")[:2000],
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "upvotes": post.get("score", 0),
                "comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc", 0),
                "created_at": created.isoformat(),
            })
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError) as e:
        print(f"  ⚠ Failed to fetch r/{subreddit}: {e}")

    return posts


def fetch_search(query: str, subreddit: str, lookback_days: int) -> list[dict]:
    """Search a subreddit for a specific query."""
    encoded_q = urllib.parse.quote(query)
    url = (f"https://www.reddit.com/r/{subreddit}/search.json"
           f"?q={encoded_q}&restrict_sr=on&sort=new&t=week&limit=25")

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    posts = []

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        cutoff = datetime.now() - timedelta(days=lookback_days)

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            created = datetime.fromtimestamp(post.get("created_utc", 0))
            if created < cutoff:
                continue

            posts.append({
                "subreddit": subreddit,
                "post_id": post.get("id", ""),
                "title": post.get("title", ""),
                "selftext": post.get("selftext", "")[:2000],
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "upvotes": post.get("score", 0),
                "comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc", 0),
                "created_at": created.isoformat(),
            })
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError):
        pass  # search failures are non-critical

    return posts


# ── Signal analysis ───────────────────────────────────────────────────────────

def is_relevant(post: dict) -> bool:
    """Check if a post is relevant to OpenClaw/agent skills."""
    text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
    return any(kw in text for kw in OPENCLAW_KEYWORDS)


def has_signal(post: dict) -> bool:
    """Check if a post contains a pain point or feature request signal."""
    text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
    return any(kw in text for kw in SIGNAL_KEYWORDS)


def classify_category(text: str) -> str:
    """Classify the likely skill category from text."""
    text_lower = text.lower()
    scores = {}
    for category, keywords in SKILL_CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def slugify(text: str) -> str:
    """Create a slug from text for proposal IDs."""
    slug = re.sub(r'[^a-z0-9\s-]', '', text.lower())
    slug = re.sub(r'[\s-]+', '-', slug).strip('-')
    return slug[:60]


def extract_pain_point(post: dict) -> str:
    """Extract a concise pain point summary from a post."""
    title = post.get("title", "")
    text = post.get("selftext", "")

    # Use the title as primary signal
    if len(title) > 20:
        return title[:120]

    # Fall back to first sentence of selftext
    sentences = re.split(r'[.!?\n]', text)
    for s in sentences:
        s = s.strip()
        if len(s) > 20 and any(kw in s.lower() for kw in SIGNAL_KEYWORDS):
            return s[:120]

    return title[:120] if title else "(no summary available)"


def suggest_skill_name(pain_point: str) -> str:
    """Suggest a potential skill name from a pain point."""
    words = re.findall(r'[a-z]+', pain_point.lower())
    # Remove very common words
    stopwords = {"the", "a", "an", "is", "are", "was", "to", "for", "in",
                 "on", "it", "my", "i", "how", "do", "can", "does", "when",
                 "not", "with", "that", "this", "have", "has", "and", "or",
                 "but", "be", "been", "any", "there", "just", "way", "get"}
    meaningful = [w for w in words if w not in stopwords and len(w) > 2]
    if len(meaningful) >= 2:
        return "-".join(meaningful[:3])
    return "unnamed-skill"


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_post(post: dict, lookback_days: int) -> float:
    """Score a post by signal strength."""
    score = 0.0

    # Upvotes (weight 2x)
    upvotes = max(0, post.get("upvotes", 0))
    score += min(upvotes, 100) * 0.2  # cap at 100 upvotes = 20 points

    # Comment depth (weight 1.5x)
    comments = max(0, post.get("comments", 0))
    score += min(comments, 50) * 0.3  # cap at 50 comments = 15 points

    # Keyword density (weight 1x)
    text = (post.get("title", "") + " " + post.get("selftext", "")).lower()
    signal_hits = sum(1 for kw in SIGNAL_KEYWORDS if kw in text)
    score += min(signal_hits, 8) * 1.0  # cap at 8 hits = 8 points

    # Recency (weight 1.5x, 7-day decay)
    age_seconds = time.time() - post.get("created_utc", time.time())
    age_days = age_seconds / 86400
    recency_factor = max(0, 1.0 - (age_days / (lookback_days + 4)))
    score *= (0.5 + 0.5 * recency_factor)  # decay to 50% at lookback boundary

    return round(score, 2)


def score_proposal(sources: list) -> float:
    """Score a proposal based on its aggregated sources."""
    total = sum(s.get("score", 0) for s in sources)

    # Recurrence bonus (weight 3x)
    recurrence = len(sources)
    if recurrence > 1:
        total += recurrence * 3.0

    # Cross-subreddit bonus
    unique_subs = len(set(s.get("subreddit", "") for s in sources))
    if unique_subs > 1:
        total += unique_subs * 2.0

    return round(total, 2)


# ── Proposal generation ──────────────────────────────────────────────────────

def build_proposals(posts: list, lookback_days: int,
                    actioned_ids: set) -> list[dict]:
    """Build scored proposals from relevant posts."""
    # Filter for relevant + signal posts
    candidates = []
    for post in posts:
        if is_relevant(post) and has_signal(post):
            post["score"] = score_post(post, lookback_days)
            candidates.append(post)

    if not candidates:
        return []

    # Group by pain point similarity (simple: by shared keywords)
    proposals = {}
    for post in candidates:
        pain = extract_pain_point(post)
        slug = slugify(pain)

        if slug in actioned_ids:
            continue

        if slug not in proposals:
            proposals[slug] = {
                "id": slug,
                "title": pain,
                "pain_point": pain,
                "potential_skill": suggest_skill_name(pain),
                "category": classify_category(pain + " " + post.get("selftext", "")),
                "sources": [],
                "first_seen_at": datetime.now().isoformat(),
                "times_seen": 0,
            }

        proposals[slug]["sources"].append({
            "subreddit": post["subreddit"],
            "post_title": post.get("title", ""),
            "url": post.get("url", ""),
            "upvotes": post.get("upvotes", 0),
            "comments": post.get("comments", 0),
            "score": post.get("score", 0),
            "fetched_at": datetime.now().isoformat(),
        })
        proposals[slug]["times_seen"] = len(proposals[slug]["sources"])

    # Score each proposal
    result = []
    for p in proposals.values():
        p["score"] = score_proposal(p["sources"])
        result.append(p)

    result.sort(key=lambda x: x["score"], reverse=True)
    return result


# ── PROPOSALS.md writer ───────────────────────────────────────────────────────

def write_proposals_md(proposals: list, subreddits: list,
                       posts_fetched: int) -> None:
    """Write PROPOSALS.md to the repo root."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Skill Proposals — Community Radar",
        "",
        f"*Last scanned: {now} | {len(subreddits)} subreddits | "
        f"{posts_fetched} posts fetched | {len(proposals)} candidates*",
        "",
        "---",
        "",
    ]

    high = [p for p in proposals if p["score"] >= 8.0]
    medium = [p for p in proposals if 4.0 <= p["score"] < 8.0]
    low = [p for p in proposals if p["score"] < 4.0]

    if high:
        lines.append("## High Signal (score >= 8.0)")
        lines.append("")
        for i, p in enumerate(high, 1):
            lines.extend(_format_proposal(i, p))
        lines.append("")

    if medium:
        lines.append("## Medium Signal (score 4.0-8.0)")
        lines.append("")
        for i, p in enumerate(medium, 1):
            lines.extend(_format_proposal(i, p))
        lines.append("")

    if low:
        lines.append("## Low Signal (score < 4.0)")
        lines.append("")
        for i, p in enumerate(low, 1):
            lines.extend(_format_proposal(i, p))
        lines.append("")

    if not proposals:
        lines.append("*No new proposals found this scan.*")
        lines.append("")

    lines.extend([
        "---",
        "",
        "*Generated by `community-skill-radar`. "
        "Run `python3 radar.py --mark-actioned <id>` to dismiss a proposal.*",
    ])

    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text("\n".join(lines) + "\n")


def _format_proposal(idx: int, p: dict) -> list[str]:
    lines = []
    lines.append(f"### {idx}. {p['title']} (score: {p['score']})")
    lines.append(f"- **Category:** {p.get('category', 'general')}")
    lines.append(f"- **Potential skill name:** `{p['potential_skill']}`")
    lines.append(f"- **Times seen:** {p['times_seen']}")

    for src in p.get("sources", [])[:3]:
        lines.append(
            f"- **Source:** r/{src['subreddit']} — "
            f"\"{src['post_title'][:80]}\" "
            f"({src['upvotes']} upvotes, {src['comments']} comments)"
        )
        if src.get("url"):
            lines.append(f"  - {src['url']}")

    lines.append("")
    return lines


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(state: dict, subreddits: list, lookback_days: int,
             min_score: float, fmt: str) -> None:
    actioned = set(a.get("id", "") for a in (state.get("actioned") or []))
    all_posts = []

    print(f"\nCommunity Skill Radar — scanning {len(subreddits)} subreddits "
          f"(last {lookback_days} days)")
    print("─" * 50)

    for sub in subreddits:
        print(f"  Fetching r/{sub}...", end=" ", flush=True)
        posts = fetch_subreddit(sub, lookback_days)
        time.sleep(RATE_LIMIT_SECONDS)

        # Also search for "openclaw" specifically in non-openclaw subs
        if sub.lower() != "openclaw":
            search_posts = fetch_search("openclaw", sub, lookback_days)
            time.sleep(RATE_LIMIT_SECONDS)
            # Deduplicate by post_id
            seen_ids = {p["post_id"] for p in posts}
            for sp in search_posts:
                if sp["post_id"] not in seen_ids:
                    posts.append(sp)

        print(f"{len(posts)} posts")
        all_posts.extend(posts)

    # Build and score proposals
    proposals = build_proposals(all_posts, lookback_days, actioned)

    if min_score > 0:
        proposals = [p for p in proposals if p["score"] >= min_score]

    # Merge with existing proposals (bump times_seen for recurring)
    existing = {p["id"]: p for p in (state.get("proposals") or [])}
    for p in proposals:
        if p["id"] in existing:
            old = existing[p["id"]]
            p["first_seen_at"] = old.get("first_seen_at", p["first_seen_at"])
            p["times_seen"] = old.get("times_seen", 0) + len(p.get("sources", []))
            # Recurrence boost
            p["score"] = round(p["score"] + old.get("times_seen", 0) * 1.5, 2)

    # Write PROPOSALS.md
    write_proposals_md(proposals, subreddits, len(all_posts))

    # Print summary
    high = sum(1 for p in proposals if p["score"] >= 8.0)
    medium = sum(1 for p in proposals if 4.0 <= p["score"] < 8.0)
    low = sum(1 for p in proposals if p["score"] < 4.0)

    print()
    print(f"  Posts fetched   : {len(all_posts)}")
    print(f"  Candidates found: {len(proposals)}")
    print(f"  High signal     : {high}")
    print(f"  Medium signal   : {medium}")
    print(f"  Low signal      : {low}")
    print(f"\n  Written to: {PROPOSALS_FILE}")
    print()

    if fmt == "json":
        print(json.dumps({
            "scanned_at": datetime.now().isoformat(),
            "subreddits": subreddits,
            "posts_fetched": len(all_posts),
            "proposals": proposals,
        }, indent=2))

    # Persist state
    now = datetime.now().isoformat()
    history = state.get("scan_history") or []
    history.insert(0, {
        "scanned_at": now,
        "subreddits": len(subreddits),
        "posts_fetched": len(all_posts),
        "candidates_found": len(proposals),
        "proposals_written": high + medium + low,
    })
    state["scan_history"] = history[:MAX_HISTORY]
    state["last_scan_at"] = now
    state["subreddits"] = subreddits
    state["proposals"] = proposals
    save_state(state)


def cmd_mark_actioned(state: dict, proposal_id: str, action: str) -> None:
    actioned = state.get("actioned") or []
    actioned.append({
        "id": proposal_id,
        "actioned_at": datetime.now().isoformat(),
        "action": action,
    })
    state["actioned"] = actioned

    # Remove from active proposals
    proposals = state.get("proposals") or []
    state["proposals"] = [p for p in proposals if p.get("id") != proposal_id]

    save_state(state)
    print(f"✓ Marked '{proposal_id}' as {action}. Won't be re-proposed.")


def cmd_status(state: dict) -> None:
    last = state.get("last_scan_at", "never")
    subs = state.get("subreddits") or []
    proposals = state.get("proposals") or []
    actioned = state.get("actioned") or []

    print(f"\nCommunity Skill Radar — Last scan: {last}")
    print(f"  Subreddits : {', '.join(subs) if subs else 'none'}")
    print(f"  Proposals  : {len(proposals)} active, {len(actioned)} actioned")

    if proposals:
        top = proposals[:3]
        print(f"\n  Top proposals:")
        for p in top:
            print(f"    [{p['score']:5.1f}] {p['title'][:60]}")
    print()


def cmd_history(state: dict) -> None:
    history = state.get("scan_history") or []
    if not history:
        print("No scan history yet.")
        return

    print(f"\nScan History ({len(history)} scans)")
    print("─" * 50)
    for h in history:
        print(f"  {h.get('scanned_at','')[:16]}  "
              f"{h.get('subreddits',0)} subs  "
              f"{h.get('posts_fetched',0)} posts  "
              f"{h.get('candidates_found',0)} candidates  "
              f"{h.get('proposals_written',0)} written")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Community Skill Radar")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true")
    group.add_argument("--mark-actioned", metavar="ID")
    group.add_argument("--status", action="store_true")
    group.add_argument("--history", action="store_true")
    parser.add_argument("--subreddits", default=None,
                        help="Comma-separated subreddits (default: built-in list)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help=f"Days to look back (default: {DEFAULT_LOOKBACK_DAYS})")
    parser.add_argument("--min-score", type=float, default=0.0,
                        help="Minimum score threshold")
    parser.add_argument("--action", default="actioned",
                        help="Action label for --mark-actioned (built/issue-filed/rejected)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        cmd_status(state)
    elif args.history:
        cmd_history(state)
    elif args.mark_actioned:
        cmd_mark_actioned(state, args.mark_actioned, args.action)
    elif args.scan:
        subreddits = (args.subreddits.split(",") if args.subreddits
                      else DEFAULT_SUBREDDITS)
        cmd_scan(state, subreddits, args.lookback, args.min_score, args.format)


if __name__ == "__main__":
    main()
