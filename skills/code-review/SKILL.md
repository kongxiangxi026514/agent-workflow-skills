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

## Adversarial review mode (对抗式审查)

用于安全 / 性能 / 并发敏感或高风险改动,叠加在上面 7 层之上;普通低风险改动只走 7 层即可。切换为严苛审查者视角,主动尝试打破代码。四个攻击维度,每条发现按 `[file:line] · 类型 · 影响 · 修复建议` 记录,并标 BLOCKING / NIT:

- **异常 / 边界输入** — malformed / 空 / 超大 / 编码 / 负数 / null;边界与 off-by-one。
- **并发 / 状态** — race、共享可变状态、执行顺序、重入、死锁、部分失败。
- **安全** — injection、path traversal、反序列化、密钥泄漏、未校验外部输入、越权。
- **性能** — 热路径分配、N+1 / 二次复杂度、无界内存、阻塞 IO、缺少背压。
