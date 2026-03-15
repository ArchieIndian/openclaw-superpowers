#!/usr/bin/env python3
"""
Skill Trigger Tester for openclaw-superpowers.

Scores a skill description's trigger quality against sample prompts.
Predicts whether OpenClaw will correctly fire the skill — before publish.

Usage:
    python3 test.py --description "Diagnoses skill failures" \\
      --should-fire "why isn't my skill loading" "skill disappeared" \\
      --should-not-fire "write a skill" "install openclaw"

    python3 test.py --file trigger-tests.yaml
    python3 test.py --file spec.yaml --compare "Alternative description here"
    python3 test.py --format json --file spec.yaml
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ── Tokeniser ─────────────────────────────────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "it",
    "its", "this", "that", "these", "those", "my", "your", "our", "their",
    "i", "you", "we", "they", "he", "she", "not", "no", "so", "if",
}


def tokenise(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 1}


# ── Synonyms ──────────────────────────────────────────────────────────────────

_SYNONYMS: list[set[str]] = [
    {"check", "verify", "validate", "test", "inspect", "audit", "scan"},
    {"fix", "repair", "resolve", "remediate", "correct"},
    {"find", "detect", "discover", "locate", "identify"},
    {"create", "write", "build", "make", "generate", "add"},
    {"run", "execute", "launch", "start", "trigger", "invoke", "fire"},
    {"skill", "skills", "extension", "extensions", "plugin", "plugins"},
    {"install", "installed", "setup", "configure"},
    {"error", "errors", "failure", "failures", "broken", "issue", "issues", "problem"},
    {"load", "loading", "loads"},
    {"missing", "gone", "disappeared", "absent"},
    {"memory", "remember", "recall", "stored"},
    {"schedule", "scheduled", "cron", "recurring", "automatic"},
    {"cost", "spend", "budget", "expensive", "usage"},
]


def expand_synonyms(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for group in _SYNONYMS:
        if tokens & group:
            expanded |= group
    return expanded


# ── Match scoring ─────────────────────────────────────────────────────────────

def description_tokens(description: str) -> set[str]:
    return expand_synonyms(tokenise(description))


def prompt_matches(prompt: str, desc_tokens: set[str]) -> bool:
    ptokens = expand_synonyms(tokenise(prompt))
    overlap = ptokens & desc_tokens
    if not ptokens:
        return False
    score = len(overlap) / len(ptokens)
    return score >= 0.25  # 25% token overlap threshold


# ── Grading ───────────────────────────────────────────────────────────────────

def grade(f1: float) -> str:
    if f1 >= 0.85:
        return "A"
    if f1 >= 0.70:
        return "B"
    if f1 >= 0.55:
        return "C"
    if f1 >= 0.40:
        return "D"
    return "F"


# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse(description: str, should_fire: list[str],
            should_not_fire: list[str]) -> dict:
    desc_tokens = description_tokens(description)

    tp_matches = [p for p in should_fire if prompt_matches(p, desc_tokens)]
    fp_matches = [p for p in should_not_fire if prompt_matches(p, desc_tokens)]
    fn_misses = [p for p in should_fire if not prompt_matches(p, desc_tokens)]
    tn_correct = [p for p in should_not_fire if not prompt_matches(p, desc_tokens)]

    recall = len(tp_matches) / len(should_fire) if should_fire else 1.0
    precision = (len(tp_matches) / (len(tp_matches) + len(fp_matches))
                 if (tp_matches or fp_matches) else 1.0)
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)

    suggestions = []
    for miss in fn_misses:
        miss_tokens = tokenise(miss) - _STOPWORDS
        missing = miss_tokens - desc_tokens
        if missing:
            suggestions.append(
                f"False negative: \"{miss}\" — consider adding: "
                + ", ".join(f'"{t}"' for t in sorted(missing)[:3])
            )
        else:
            suggestions.append(f"False negative: \"{miss}\" — check synonym coverage")

    for fp in fp_matches:
        suggestions.append(
            f"False positive: \"{fp}\" — narrow description to reduce overlap"
        )

    return {
        "description": description,
        "recall": round(recall, 3),
        "precision": round(precision, 3),
        "f1": round(f1, 3),
        "grade": grade(f1),
        "should_fire_total": len(should_fire),
        "should_fire_matched": len(tp_matches),
        "should_not_fire_total": len(should_not_fire),
        "should_not_fire_mismatched": len(fp_matches),
        "false_negatives": fn_misses,
        "false_positives": fp_matches,
        "suggestions": suggestions,
    }


# ── Output ────────────────────────────────────────────────────────────────────

def print_result(result: dict, label: str = "") -> None:
    header = f"Skill Trigger Quality{' — ' + label if label else ''}"
    print(f"\n{header}")
    print("─" * 48)
    desc = result["description"]
    print(f"Description: \"{desc[:80]}{'...' if len(desc) > 80 else ''}\"")
    print()
    print(f"  Should fire    ({result['should_fire_total']:2d} prompts): "
          f"{result['should_fire_matched']:2d} matched   "
          f"recall    = {result['recall']:.2f}")
    print(f"  Should not fire({result['should_not_fire_total']:2d} prompts): "
          f"{result['should_not_fire_mismatched']:2d} matched   "
          f"precision = {result['precision']:.2f}")
    print()
    print(f"  F1 score: {result['f1']:.2f}   Grade: {result['grade']}")

    if result["suggestions"]:
        print()
        for s in result["suggestions"]:
            print(f"  ⚠ {s}")
    print()


def print_comparison(r1: dict, r2: dict) -> None:
    print("\nDescription Comparison")
    print("─" * 48)
    for label, r in [("Option A (original)", r1), ("Option B (alternative)", r2)]:
        print(f"  {label}: F1={r['f1']:.2f} Grade={r['grade']} "
              f"(recall={r['recall']:.2f}, precision={r['precision']:.2f})")
    winner = "A" if r1["f1"] >= r2["f1"] else "B"
    print(f"\n  → Option {winner} scores higher.")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def load_spec(path: str) -> dict:
    if not HAS_YAML:
        print("ERROR: pyyaml required for --file. Install with: pip install pyyaml")
        sys.exit(1)
    text = Path(path).read_text()
    return yaml.safe_load(text) or {}


def main():
    parser = argparse.ArgumentParser(description="Skill Trigger Tester")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--description", metavar="TEXT",
                     help="Description string to test")
    src.add_argument("--file", metavar="YAML",
                     help="Load test spec from YAML file")
    parser.add_argument("--should-fire", nargs="+", metavar="PROMPT", default=[],
                        help="Prompts that should trigger the skill")
    parser.add_argument("--should-not-fire", nargs="+", metavar="PROMPT", default=[],
                        help="Prompts that should NOT trigger the skill")
    parser.add_argument("--compare", metavar="ALT_DESC",
                        help="Alternative description to compare against")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.file:
        spec = load_spec(args.file)
        description = spec.get("description", "")
        should_fire = spec.get("should_fire", [])
        should_not_fire = spec.get("should_not_fire", [])
    else:
        description = args.description
        should_fire = args.should_fire
        should_not_fire = args.should_not_fire

    if not should_fire and not should_not_fire:
        print("ERROR: Provide at least one --should-fire or --should-not-fire prompt.")
        sys.exit(1)

    result = analyse(description, should_fire, should_not_fire)

    alt_result = None
    if args.compare:
        alt_result = analyse(args.compare, should_fire, should_not_fire)

    if args.format == "json":
        output = {"primary": result}
        if alt_result:
            output["alternative"] = alt_result
        print(json.dumps(output, indent=2))
    else:
        print_result(result, label=description[:40])
        if alt_result:
            print_result(alt_result, label="Alternative")
            print_comparison(result, alt_result)

    sys.exit(0 if result["grade"] in ("A", "B") else 1)


if __name__ == "__main__":
    main()
