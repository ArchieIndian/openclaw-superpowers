#!/usr/bin/env python3
"""
Tool Description Optimizer for openclaw-superpowers.

Scores skill descriptions for trigger quality and suggests rewrites.

Usage:
    python3 optimize.py --scan
    python3 optimize.py --scan --grade C
    python3 optimize.py --skill <name>
    python3 optimize.py --suggest <name>
    python3 optimize.py --compare "desc A" "desc B"
    python3 optimize.py --status
    python3 optimize.py --format json
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "tool-description-optimizer" / "state.yaml"
MAX_HISTORY = 20

# Skill directories to scan
SKILL_DIRS = [
    Path(__file__).resolve().parent.parent.parent,  # repo skills/ root
]

# ── Scoring constants ────────────────────────────────────────────────────────

VAGUE_WORDS = {
    "helps", "manages", "handles", "deals", "works", "does", "stuff",
    "various", "things", "general", "misc", "miscellaneous", "utility",
    "tool", "assistant", "helper", "processor", "handler", "manager",
    "simple", "basic", "easy", "nice", "good", "great",
}

STRONG_VERBS = {
    "scans", "detects", "validates", "generates", "audits", "monitors",
    "checks", "reports", "fixes", "migrates", "syncs", "schedules",
    "blocks", "scores", "diagnoses", "parses", "extracts", "compiles",
    "compacts", "deduplicates", "prunes", "enforces", "breaks", "chains",
    "writes", "creates", "builds", "searches", "filters", "tracks",
    "prevents", "recovers", "resumes", "verifies", "tests", "measures",
}

STRONG_NOUNS = {
    "api", "key", "token", "secret", "credential", "permission",
    "cron", "schedule", "context", "memory", "state", "schema",
    "skill", "agent", "session", "task", "workflow", "budget",
    "injection", "drift", "conflict", "error", "failure", "loop",
    "graph", "node", "edge", "digest", "report", "proposal",
    "reddit", "github", "slack", "config", "yaml", "json",
}

OPTIMAL_LENGTH = 25  # words
LENGTH_SIGMA = 10    # std dev for bell curve

GRADE_THRESHOLDS = [
    (8.0, "A"), (6.0, "B"), (4.0, "C"), (2.0, "D"), (0.0, "F"),
]


# ── State helpers ────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"skill_scores": [], "scan_history": []}
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


# ── Skill discovery ──────────────────────────────────────────────────────────

def discover_skills() -> list[dict]:
    """Find all installed skills and extract their descriptions."""
    skills = []
    for skill_root in SKILL_DIRS:
        if not skill_root.exists():
            continue
        for category_dir in sorted(skill_root.iterdir()):
            if not category_dir.is_dir():
                continue
            for skill_dir in sorted(category_dir.iterdir()):
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                desc = extract_description(skill_md)
                if desc:
                    skills.append({
                        "name": skill_dir.name,
                        "category": category_dir.name,
                        "description": desc,
                    })
    return skills


def extract_description(skill_md: Path) -> str:
    """Extract description from SKILL.md frontmatter."""
    try:
        text = skill_md.read_text()
    except (PermissionError, OSError):
        return ""
    # Parse YAML frontmatter
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    frontmatter = text[3:end].strip()
    for line in frontmatter.split("\n"):
        if line.startswith("description:"):
            desc = line[len("description:"):].strip().strip("\"'")
            return desc
    return ""


# ── Scoring ──────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def score_clarity(tokens: list[str]) -> float:
    """Score clarity: penalize vague words, reward single clear purpose."""
    if not tokens:
        return 0.0
    vague_count = sum(1 for t in tokens if t in VAGUE_WORDS)
    vague_ratio = vague_count / len(tokens)
    # Penalize heavily for high vague ratio
    score = 10.0 * (1.0 - vague_ratio * 2.5)
    # Bonus for having a verb early (signals clear purpose)
    for t in tokens[:5]:
        if t in STRONG_VERBS:
            score += 1.0
            break
    return max(0.0, min(10.0, score))


def score_specificity(tokens: list[str]) -> float:
    """Score specificity: strong verbs and concrete nouns."""
    if not tokens:
        return 0.0
    verb_count = sum(1 for t in tokens if t in STRONG_VERBS)
    noun_count = sum(1 for t in tokens if t in STRONG_NOUNS)
    strong_ratio = (verb_count + noun_count) / len(tokens)
    score = min(10.0, strong_ratio * 25.0)
    return max(0.0, score)


def score_keyword_density(tokens: list[str]) -> float:
    """Score keyword density: trigger-relevant terms per token."""
    if not tokens:
        return 0.0
    all_keywords = STRONG_VERBS | STRONG_NOUNS
    keyword_count = sum(1 for t in tokens if t in all_keywords)
    density = keyword_count / len(tokens)
    score = min(10.0, density * 30.0)
    return max(0.0, score)


def score_uniqueness(tokens_set: set, all_other_sets: list[set]) -> float:
    """Score uniqueness: low Jaccard similarity to other descriptions."""
    if not all_other_sets:
        return 10.0
    max_sim = max(jaccard(tokens_set, other) for other in all_other_sets)
    # 0.0 similarity = 10.0 score, 1.0 similarity = 0.0 score
    score = 10.0 * (1.0 - max_sim)
    return max(0.0, min(10.0, score))


def score_length(word_count: int) -> float:
    """Score length: bell curve centered on OPTIMAL_LENGTH."""
    z = (word_count - OPTIMAL_LENGTH) / LENGTH_SIGMA
    score = 10.0 * math.exp(-0.5 * z * z)
    return max(0.0, min(10.0, score))


def compute_overall(clarity, specificity, keyword_density, uniqueness, length_score) -> float:
    """Weighted composite score."""
    weighted = (
        clarity * 2.0 +
        specificity * 2.0 +
        keyword_density * 1.5 +
        uniqueness * 1.5 +
        length_score * 1.0
    )
    total_weight = 2.0 + 2.0 + 1.5 + 1.5 + 1.0
    return round(weighted / total_weight, 1)


def get_grade(score: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def score_description(desc: str, all_other_descs: list[str]) -> dict:
    """Full scoring of a single description."""
    tokens = tokenize(desc)
    tokens_set = set(tokens)
    other_sets = [set(tokenize(d)) for d in all_other_descs]
    word_count = len(desc.split())

    clarity = round(score_clarity(tokens), 1)
    specificity = round(score_specificity(tokens), 1)
    keyword_density = round(score_keyword_density(tokens), 1)
    uniqueness = round(score_uniqueness(tokens_set, other_sets), 1)
    length = round(score_length(word_count), 1)
    overall = compute_overall(clarity, specificity, keyword_density, uniqueness, length)
    grade = get_grade(overall)

    return {
        "word_count": word_count,
        "clarity": clarity,
        "specificity": specificity,
        "keyword_density": keyword_density,
        "uniqueness": uniqueness,
        "length_score": length,
        "overall": overall,
        "grade": grade,
    }


# ── Suggestion engine ────────────────────────────────────────────────────────

def suggest_rewrites(name: str, desc: str, all_other_descs: list[str]) -> list[dict]:
    """Generate 2-3 rewrite suggestions with predicted improvements."""
    suggestions = []
    tokens = tokenize(desc)
    words = desc.split()

    # Strategy 1: Replace vague words with strong verbs
    rewrite1_words = []
    replacements = {
        "helps": "assists", "manages": "tracks", "handles": "processes",
        "deals": "resolves", "works": "operates", "does": "executes",
    }
    changed = False
    for w in words:
        low = w.lower().rstrip(".,;:")
        if low in VAGUE_WORDS and low in replacements:
            rewrite1_words.append(replacements[low])
            changed = True
        else:
            rewrite1_words.append(w)
    if changed:
        rewrite1 = " ".join(rewrite1_words)
        s1 = score_description(rewrite1, all_other_descs)
        suggestions.append({
            "strategy": "Replace vague words",
            "rewrite": rewrite1,
            "predicted_score": s1["overall"],
            "predicted_grade": s1["grade"],
        })

    # Strategy 2: Trim to optimal length if too long
    if len(words) > 40:
        trimmed = " ".join(words[:35])
        if not trimmed.endswith("."):
            trimmed += "."
        s2 = score_description(trimmed, all_other_descs)
        suggestions.append({
            "strategy": "Trim to optimal length",
            "rewrite": trimmed,
            "predicted_score": s2["overall"],
            "predicted_grade": s2["grade"],
        })

    # Strategy 3: Front-load with action verb if none in first 3 words
    first_tokens = tokenize(" ".join(words[:3]))
    has_verb = any(t in STRONG_VERBS for t in first_tokens)
    if not has_verb:
        # Try to extract the main verb from the description
        for t in tokens:
            if t in STRONG_VERBS:
                verb = t.capitalize() + "s"
                rewrite3 = f"{verb} {desc[0].lower()}{desc[1:]}"
                s3 = score_description(rewrite3, all_other_descs)
                suggestions.append({
                    "strategy": "Front-load action verb",
                    "rewrite": rewrite3,
                    "predicted_score": s3["overall"],
                    "predicted_grade": s3["grade"],
                })
                break

    if not suggestions:
        suggestions.append({
            "strategy": "No automatic rewrites — description already scores well",
            "rewrite": desc,
            "predicted_score": score_description(desc, all_other_descs)["overall"],
            "predicted_grade": score_description(desc, all_other_descs)["grade"],
        })

    return suggestions


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_scan(state: dict, grade_filter: str, fmt: str) -> None:
    skills = discover_skills()
    now = datetime.now().isoformat()
    all_descs = [s["description"] for s in skills]
    results = []

    for i, skill in enumerate(skills):
        other_descs = all_descs[:i] + all_descs[i+1:]
        scores = score_description(skill["description"], other_descs)
        scores["skill_name"] = skill["name"]
        scores["description"] = skill["description"]
        results.append(scores)

    # Sort by overall score ascending (worst first)
    results.sort(key=lambda r: r["overall"])

    # Apply grade filter
    if grade_filter:
        grade_order = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}
        cutoff = grade_order.get(grade_filter.upper(), 2)
        results = [r for r in results if grade_order.get(r["grade"], 0) <= cutoff]

    # Grade distribution
    dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    all_results = []
    for i, skill in enumerate(skills):
        other_descs = all_descs[:i] + all_descs[i+1:]
        scores = score_description(skill["description"], other_descs)
        dist[scores["grade"]] = dist.get(scores["grade"], 0) + 1
        scores["skill_name"] = skill["name"]
        scores["description"] = skill["description"]
        all_results.append(scores)

    avg_score = round(sum(r["overall"] for r in all_results) / len(all_results), 1) if all_results else 0.0

    if fmt == "json":
        print(json.dumps({"skills_scanned": len(skills), "results": results, "avg_score": avg_score, "grades": dist}, indent=2))
    else:
        print(f"\nTool Description Quality Scan — {datetime.now().strftime('%Y-%m-%d')}")
        print("-" * 60)
        print(f"  {len(skills)} skills scanned | avg score: {avg_score}")
        print(f"  Grades: {dist['A']}xA  {dist['B']}xB  {dist['C']}xC  {dist['D']}xD  {dist['F']}xF")
        print()
        if not results:
            print("  All skills above grade threshold.")
        else:
            for r in results:
                icon = {"A": "+", "B": "+", "C": "~", "D": "!", "F": "x"}
                print(f"  {icon.get(r['grade'], '?')} [{r['grade']}] {r['overall']:>4} — {r['skill_name']}")
                print(f"         clarity={r['clarity']} spec={r['specificity']} kw={r['keyword_density']} "
                      f"uniq={r['uniqueness']} len={r['length_score']}")
                # Truncate description for display
                desc = r["description"]
                if len(desc) > 80:
                    desc = desc[:77] + "..."
                print(f"         \"{desc}\"")
                print()

    # Persist
    state["last_scan_at"] = now
    state["skill_scores"] = all_results
    history = state.get("scan_history") or []
    history.insert(0, {
        "scanned_at": now, "skills_scanned": len(skills),
        "avg_score": avg_score, "grade_distribution": dist,
    })
    state["scan_history"] = history[:MAX_HISTORY]
    save_state(state)


def cmd_skill(state: dict, name: str, fmt: str) -> None:
    skills = discover_skills()
    target = None
    for s in skills:
        if s["name"] == name:
            target = s
            break
    if not target:
        print(f"Error: skill '{name}' not found.")
        sys.exit(1)

    all_descs = [s["description"] for s in skills if s["name"] != name]
    scores = score_description(target["description"], all_descs)

    if fmt == "json":
        scores["skill_name"] = name
        scores["description"] = target["description"]
        print(json.dumps(scores, indent=2))
    else:
        print(f"\nDeep Analysis: {name}")
        print("-" * 50)
        print(f"  Description: \"{target['description']}\"")
        print(f"  Word count:  {scores['word_count']}")
        print()
        print(f"  Clarity:          {scores['clarity']:>4}/10  {'||' * int(scores['clarity'])}")
        print(f"  Specificity:      {scores['specificity']:>4}/10  {'||' * int(scores['specificity'])}")
        print(f"  Keyword density:  {scores['keyword_density']:>4}/10  {'||' * int(scores['keyword_density'])}")
        print(f"  Uniqueness:       {scores['uniqueness']:>4}/10  {'||' * int(scores['uniqueness'])}")
        print(f"  Length score:     {scores['length_score']:>4}/10  {'||' * int(scores['length_score'])}")
        print(f"  ─────────────────────────")
        print(f"  Overall:          {scores['overall']:>4}/10  Grade: {scores['grade']}")
        print()

        # Show vague words found
        tokens = tokenize(target["description"])
        vague_found = [t for t in tokens if t in VAGUE_WORDS]
        if vague_found:
            print(f"  Vague words: {', '.join(set(vague_found))}")

        strong_found = [t for t in tokens if t in STRONG_VERBS | STRONG_NOUNS]
        if strong_found:
            print(f"  Strong keywords: {', '.join(set(strong_found))}")
        print()


def cmd_suggest(state: dict, name: str, fmt: str) -> None:
    skills = discover_skills()
    target = None
    for s in skills:
        if s["name"] == name:
            target = s
            break
    if not target:
        print(f"Error: skill '{name}' not found.")
        sys.exit(1)

    all_descs = [s["description"] for s in skills if s["name"] != name]
    current = score_description(target["description"], all_descs)
    suggestions = suggest_rewrites(name, target["description"], all_descs)

    if fmt == "json":
        print(json.dumps({"skill": name, "current_score": current["overall"],
                          "current_grade": current["grade"], "suggestions": suggestions}, indent=2))
    else:
        print(f"\nRewrite Suggestions: {name}")
        print("-" * 50)
        print(f"  Current: \"{target['description']}\"")
        print(f"  Score: {current['overall']} ({current['grade']})")
        print()
        for i, s in enumerate(suggestions, 1):
            delta = s["predicted_score"] - current["overall"]
            arrow = "+" if delta > 0 else ""
            print(f"  {i}. {s['strategy']}")
            print(f"     \"{s['rewrite']}\"")
            print(f"     Predicted: {s['predicted_score']} ({s['predicted_grade']}) [{arrow}{delta}]")
            print()


def cmd_compare(desc_a: str, desc_b: str, fmt: str) -> None:
    scores_a = score_description(desc_a, [desc_b])
    scores_b = score_description(desc_b, [desc_a])

    if fmt == "json":
        print(json.dumps({"a": {"description": desc_a, **scores_a},
                          "b": {"description": desc_b, **scores_b}}, indent=2))
    else:
        print(f"\nDescription Comparison")
        print("-" * 50)
        print(f"  A: \"{desc_a}\"")
        print(f"  B: \"{desc_b}\"")
        print()
        metrics = ["clarity", "specificity", "keyword_density", "uniqueness", "length_score", "overall"]
        labels = ["Clarity", "Specificity", "Keywords", "Uniqueness", "Length", "OVERALL"]
        for label, metric in zip(labels, metrics):
            va = scores_a[metric]
            vb = scores_b[metric]
            winner = "A" if va > vb else ("B" if vb > va else "=")
            print(f"  {label:12s}  A={va:<5}  B={vb:<5}  {winner}")
        print(f"\n  Grade:  A={scores_a['grade']}  B={scores_b['grade']}")
        print()


def cmd_status(state: dict) -> None:
    last = state.get("last_scan_at", "never")
    print(f"\nTool Description Optimizer — Last scan: {last}")
    history = state.get("scan_history") or []
    if history:
        h = history[0]
        print(f"  {h.get('skills_scanned', 0)} skills | avg score: {h.get('avg_score', 0)}")
        dist = h.get("grade_distribution", {})
        print(f"  Grades: {dist.get('A',0)}xA  {dist.get('B',0)}xB  "
              f"{dist.get('C',0)}xC  {dist.get('D',0)}xD  {dist.get('F',0)}xF")
    scores = state.get("skill_scores") or []
    low = [s for s in scores if s.get("grade") in ("D", "F")]
    if low:
        print(f"\n  Low-scoring ({len(low)}):")
        for s in low[:5]:
            print(f"    [{s['grade']}] {s['overall']} — {s['skill_name']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Tool Description Optimizer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Score all installed skill descriptions")
    group.add_argument("--skill", type=str, metavar="NAME", help="Deep analysis of a single skill")
    group.add_argument("--suggest", type=str, metavar="NAME", help="Generate rewrite suggestions")
    group.add_argument("--compare", nargs=2, metavar=("DESC_A", "DESC_B"), help="Compare two descriptions")
    group.add_argument("--status", action="store_true", help="Last scan summary")
    parser.add_argument("--grade", type=str, metavar="GRADE", help="Only show skills at or below this grade (A-F)")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()
    if args.scan:
        cmd_scan(state, args.grade, args.format)
    elif args.skill:
        cmd_skill(state, args.skill, args.format)
    elif args.suggest:
        cmd_suggest(state, args.suggest, args.format)
    elif args.compare:
        cmd_compare(args.compare[0], args.compare[1], args.format)
    elif args.status:
        cmd_status(state)


if __name__ == "__main__":
    main()
