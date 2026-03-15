---
name: <skill-name>
description: <One sentence — what it does and when to use it.>
# cron: "<5-field cron expression>"   # optional: schedule this skill with OpenClaw
# stateful: true                       # optional: enables STATE_SCHEMA.yaml + runtime state dir
---

# <Skill Title>

<One-line philosophy or core principle.>

## When to Use

- <Specific trigger 1>
- <Specific trigger 2>

## The Process

### Step 1: <Action>
<What to do, concretely.>

### Step 2: <Action>
<What to do next.>

### Step 3: <Action>
<What to do after that.>

## Key Principles

- <Rule or guideline that shapes how the process is applied>
- <Another principle>

## OpenClaw-Specific Notes

<!-- Optional. Remove this section if not applicable. -->
- <Persistence, memory, or long-session consideration>

<!-- If stateful: true, create STATE_SCHEMA.yaml alongside this file:

version: "1.0"
fields:
  <field_name>:
    type: <string|enum|list|datetime|boolean|integer>
    required: <true|false>       # optional, defaults false
    default: <value>             # optional
    values: [...]                # only for type: enum
    items: { type: ... }         # only for type: list
    description: "..."           # optional annotation
-->
