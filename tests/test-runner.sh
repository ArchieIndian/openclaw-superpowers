#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
PASS=0; FAIL=0
for skill_dir in "$SKILLS_DIR"/**/*; do
  if [ -d "$skill_dir" ]; then
    skill_name="$(basename "$skill_dir")"
    label="$skill_name"

    # Check SKILL.md exists
    if [ ! -f "$skill_dir/SKILL.md" ]; then
      echo "FAIL: $skill_name missing SKILL.md"; FAIL=$((FAIL+1))
      continue
    fi

    # Check stateful coherence: stateful: true requires STATE_SCHEMA.yaml
    fm_stateful="$(sed -n '2,/^---$/p' "$skill_dir/SKILL.md" | grep '^stateful:' | sed 's/^stateful: *//' | tr -d '[:space:]' || true)"
    if [ "$fm_stateful" = "true" ] && [ ! -f "$skill_dir/STATE_SCHEMA.yaml" ]; then
      echo "FAIL: $skill_name stateful: true but STATE_SCHEMA.yaml missing"; FAIL=$((FAIL+1))
      continue
    fi

    # Check cron format if present
    fm_cron="$(sed -n '2,/^---$/p' "$skill_dir/SKILL.md" | grep '^cron:' | sed 's/^cron: *//' | tr -d '"'"'" || true)"
    if [ -n "$fm_cron" ]; then
      if ! echo "$fm_cron" | grep -qE '^[0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+$'; then
        echo "FAIL: $skill_name invalid cron expression '$fm_cron'"; FAIL=$((FAIL+1))
        continue
      fi
    fi

    # Append [stateful] tag to label when applicable
    if [ "$fm_stateful" = "true" ]; then
      label="$skill_name [stateful]"
    fi

    echo "PASS: $label"; PASS=$((PASS+1))
  fi
done
"$REPO_DIR/scripts/check-readme-metrics.sh"
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
