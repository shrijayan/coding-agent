---
name: git-commit-style
description: How to write a commit message for a change - use when asked to commit work with git.
---
When writing a commit message:

- Subject line under 50 characters, imperative mood ("Add divide-by-zero
  check", not "Added" or "Adding").
- Explain *why* the change was made in the body, not a restatement of the
  diff - the diff already shows what changed.
- One logical change per commit. If a change bundles an unrelated fix and
  a new feature, split it into two commits.
- Never mention an internal task ID or reviewer name the reader of the
  history won't have context for.
