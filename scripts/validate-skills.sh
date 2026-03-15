#!/usr/bin/env bash
set -euo pipefail

# Validates all skills in the repository.
# Run manually or via CI on pull requests.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
ERRORS=0

validate_skill() {
  local skill_dir="$1"
  local skill_file="$skill_dir/SKILL.md"
  local dir_name
  dir_name="$(basename "$skill_dir")"

  # Check SKILL.md exists
  if [ ! -f "$skill_file" ]; then
    echo "FAIL: $skill_dir — missing SKILL.md"
    ERRORS=$((ERRORS + 1))
    return
  fi

  # Check frontmatter exists
  local first_line
  first_line="$(head -1 "$skill_file")"
  if [ "$first_line" != "---" ]; then
    echo "FAIL: $dir_name — missing frontmatter (file must start with ---)"
    ERRORS=$((ERRORS + 1))
    return
  fi

  # Extract frontmatter name
  local fm_name
  fm_name="$(sed -n '2,/^---$/p' "$skill_file" | grep '^name:' | sed 's/^name: *//' | tr -d '[:space:]')"
  if [ -z "$fm_name" ]; then
    echo "FAIL: $dir_name — frontmatter missing 'name' field"
    ERRORS=$((ERRORS + 1))
  elif [ "$fm_name" != "$dir_name" ]; then
    echo "FAIL: $dir_name — frontmatter name '$fm_name' does not match directory name '$dir_name'"
    ERRORS=$((ERRORS + 1))
  fi

  # Extract frontmatter description
  local fm_desc
  fm_desc="$(sed -n '2,/^---$/p' "$skill_file" | grep '^description:' | sed 's/^description: *//')"
  if [ -z "$fm_desc" ]; then
    echo "FAIL: $dir_name — frontmatter missing 'description' field"
    ERRORS=$((ERRORS + 1))
  fi

  # Check directory name is kebab-case
  if ! echo "$dir_name" | grep -qE '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'; then
    echo "FAIL: $dir_name — directory name must be kebab-case"
    ERRORS=$((ERRORS + 1))
  fi

  # Check line count (warn over 80)
  local line_count
  line_count="$(wc -l < "$skill_file" | tr -d '[:space:]')"
  if [ "$line_count" -gt 80 ]; then
    echo "WARN: $dir_name — $line_count lines (recommended: under 80)"
  fi

  # Extract optional cron field
  local fm_cron
  fm_cron="$(sed -n '2,/^---$/p' "$skill_file" | grep '^cron:' | sed 's/^cron: *//' | tr -d '"'"'" || true)"
  if [ -n "$fm_cron" ]; then
    # Validate 5-field cron expression format
    if ! echo "$fm_cron" | grep -qE '^[0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+ [0-9*/,\-]+$'; then
      echo "FAIL: $dir_name — invalid cron expression '$fm_cron' (must be 5 space-separated fields)"
      ERRORS=$((ERRORS + 1))
    fi
  fi

  # Extract optional stateful field
  local fm_stateful
  fm_stateful="$(sed -n '2,/^---$/p' "$skill_file" | grep '^stateful:' | sed 's/^stateful: *//' | tr -d '[:space:]' || true)"

  # If stateful: true, STATE_SCHEMA.yaml must exist
  if [ "$fm_stateful" = "true" ]; then
    if [ ! -f "$skill_dir/STATE_SCHEMA.yaml" ]; then
      echo "FAIL: $dir_name — stateful: true but STATE_SCHEMA.yaml is missing"
      ERRORS=$((ERRORS + 1))
    fi
  fi

  # If STATE_SCHEMA.yaml exists, stateful: true must be in frontmatter
  if [ -f "$skill_dir/STATE_SCHEMA.yaml" ]; then
    if [ "$fm_stateful" != "true" ]; then
      echo "WARN: $dir_name — STATE_SCHEMA.yaml present but frontmatter missing 'stateful: true'"
    fi
    # Check STATE_SCHEMA.yaml has required keys
    if ! grep -q '^version:' "$skill_dir/STATE_SCHEMA.yaml"; then
      echo "WARN: $dir_name — STATE_SCHEMA.yaml missing 'version:' key"
    fi
    if ! grep -q '^fields:' "$skill_dir/STATE_SCHEMA.yaml"; then
      echo "WARN: $dir_name — STATE_SCHEMA.yaml missing 'fields:' key"
    fi
  fi

  # If we got here without errors for this skill, it's valid
  if [ $ERRORS -eq 0 ] 2>/dev/null; then
    echo "  OK: $dir_name"
  fi
}

echo "Validating skills..."
echo ""

for category_dir in "$SKILLS_DIR"/*/; do
  category="$(basename "$category_dir")"
  echo "[$category]"

  for skill_dir in "$category_dir"*/; do
    # Skip if no subdirectories
    [ -d "$skill_dir" ] || continue
    validate_skill "$skill_dir"
  done

  echo ""
done

if [ $ERRORS -gt 0 ]; then
  echo "Validation failed with $ERRORS error(s)."
  exit 1
else
  echo "All skills valid."
  exit 0
fi
