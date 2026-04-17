---
name: pull-request-feedback-loop
description: Handles PR review feedback by fetching comments, grouping issues, fixing one group at a time, and verifying before replies.
---

# Pull Request Feedback Loop

PR feedback is a queue of review obligations, not a pile of comments. Use this skill when a user asks you to address PR comments, requested changes, failed checks tied to review feedback, or stale review threads.

## When to Use

- A PR has unresolved review comments or requested changes
- The user asks you to "address review feedback" or "fix PR comments"
- You need to reconcile code changes, replies, and verification

Do not use this for ordinary local refactors with no review thread.

## Process

1. Identify the PR.
   - Prefer the PR number or URL from the user.
   - If missing, run `gh pr status` or `gh pr view --json number,url,headRefName`.

2. Fetch review context.
   - Run `gh pr view <pr> --comments`.
   - If needed, run `gh api` for review threads or inline comments.
   - Capture author, file, line, status, and requested change.

3. Group comments by issue.
   - Merge duplicate comments that point at the same underlying fix.
   - Separate behavior bugs, test gaps, naming/docs cleanup, and questions.
   - Mark comments that need clarification before code changes.

4. Fix one group at a time.
   - Inspect the referenced code before editing.
   - Make the smallest coherent change for that group.
   - Avoid bundling unrelated cleanup into review fixes.

5. Verify before replying.
   - Run the narrowest relevant test or check for each group.
   - If no test can run, explain the exact reason and inspect manually.
   - Do not claim a thread is resolved until verification passes or is explicitly waived.

6. Prepare replies.
   - Summarize what changed and how it was verified.
   - Keep replies short and factual.
   - Do not submit replies automatically unless the user asked you to.

## Output

Report:

- Groups handled
- Files changed
- Verification run
- Threads ready for reply
- Threads needing user or reviewer clarification

## Guardrails

- Do not force-push, delete branches, or dismiss reviews without explicit permission.
- Do not mark comments resolved only because code was edited.
- Do not ignore a comment because it looks small; either address it or explain why it is not applicable.
