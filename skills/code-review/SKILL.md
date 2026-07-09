---
name: code-review
description: Layered code review + no-false-negative re-verification + slimming/refactor discipline. Use when reviewing code changes, a diff, a PR, or a completed batch, or before merging. Reviewer should be a different model family than the implementer (cross-model verification).
---

# Layered Code Review

Run cross-model (reviewer ≠ implementer model family). Mark each finding **[BLOCKING]** or **[NIT]**. Review by priority:

1. Correctness / design — logic, boundary conditions, concurrency/state, contract integrity.
2. Tests — new behavior covered, failure paths, TDD RED genuinely fails.
3. Security / robustness — no hardcoded secrets, errors not swallowed, external-input validation, fail-loud (not silent fallback).
4. API / contract back-compat — public surface, snapshots, schema.
5. Readability / architecture — naming, cognitive complexity (nesting ≤3), module boundaries, comment discipline (why-not-what), no spec/plan pointers in delivery code.
6. AI-code specifics — is it human-readable? over-engineered? demo residue / narration comments / unused imports / placeholder-fake-impl?
7. Nits — style only, non-blocking.

## No-false-negative re-verification (MANDATORY)

Any NEGATIVE assertion — "no tests / no references / unused / safe to delete / dead code / uncovered" — MUST be re-verified with `rg --no-ignore` over the full tree (NOT default grep/glob), because `.worktrees/` and gitignored `*.log` are silently skipped and produce false negatives. The main agent MUST independently re-verify EVERY blocking negative assertion (rerun `rg --no-ignore` or directly read the decisive files) before accepting it. Never trust a reviewer's "missing/unused" conclusion blindly. (This rule was born from a real case: a reviewer's default-grep false negative wrongly flagged classes as untested when 4 dedicated test files existed.)

## Slimming / refactor discipline

- Refactor only under test protection (behavior-preserving needs golden/regression anchors); same tests stay green after.
- Keep refactor commits separate from behavior-change commits.
- Remove dead code / unused imports / stale shims (confirm no refs via the no-ignore check first — garbage does not get merged).
- Give large refactors a rollback point (`git checkout -- <file>`), never patch-on-patch.

## Adversarial review mode

For security / performance / concurrency-sensitive or high-risk changes; layered on top of the 7-layer pass above — ordinary low-risk changes only need the 7 layers. Switch to a harsh reviewer's perspective and actively try to break the code. Four attack dimensions; record each finding as `[file:line] | type | impact | suggested fix` and mark it BLOCKING / NIT:

- **Exceptional / boundary input** — malformed / empty / oversized / encoding / negative / null; boundaries and off-by-one.
- **Concurrency / state** — races, shared mutable state, execution ordering, reentrancy, deadlock, partial failure.
- **Security** — injection, path traversal, deserialization, secret leakage, unvalidated external input, privilege escalation.
- **Performance** — hot-path allocation, N+1 / quadratic complexity, unbounded memory, blocking IO, missing backpressure.
