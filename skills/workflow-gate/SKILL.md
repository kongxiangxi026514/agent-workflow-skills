---
name: workflow-gate
description: Per-turn workflow spine for commercial-grade dev. Use at the start of every non-trivial coding turn to pick an execution path (A/B/C/D), run as main-agent orchestrator with subagents as the workforce, and drive the grill→discovery→design→batch→execute→acceptance→closeout flow. Triggers on any implementation, refactor, debugging, or design task.
---

# Workflow Gate (spine)

Commercial-grade, human-readable, mergeable production code — not AI-only demo code. Announce one line at the start of every turn, then act.

## 1. Per-turn dual gate → path A/B/C/D

- D-size hit = change ≤5 effective lines AND single file AND no new public API / module boundary.
- D-risk hit = touches a contract surface (model heads/class counts, training loss/mask semantics, data schema, geometry/CRS, pipeline determinism, version-sensitive third-party API, cross-file protocols). When unsure, treat D-risk as HIT.
- Path A (size hit + low risk): skip main chain, run only completion-time verification.
- Path B (size hit + risk): skip brainstorm/plan/TDD, keep verification + optional review.
- Path C (risk hit): full chain brainstorm → spec → plan → TDD → verify → review.
- Path D (neither hit): simplified chain (1-2 clarifying questions → plan → TDD → verify).
- User overrides win: "走完整流程/严格 TDD" → C; "快速改一下/别走完整流程" → A/B (verification still runs).

Announce the first sentence, e.g. "本轮走简化主链(路径 D,…),…" — skipping the announcement is a violation.

## 2. Main-agent-led, subagent-heavy

Main agent orchestrates: scope, plan, dispatch, intake, synthesis, verification, user comms. Subagents do non-trivial implementation/debug/test/exploration/review. Main must NOT duplicate delegated work in the foreground, and must independently re-verify every subagent result before accepting it.

## 3. Complex/fuzzy default flow

`Grill Gate → Codebase/External Discovery → Design Brief → Batch Plan → dependency analysis (parallel vs serial subagents) → main-agent merge + write-conflict check + integrated verification → Acceptance Block → Closeout Block`. (Grill = ask 3-5 sharp questions on fuzzy ideas; see the `code-review`, `research-routing`, `parallel-dispatch`, `memory-gate` skills for those steps.)

## 4. Code quality & architecture contract (the floor is 800/100 lines + diff ≤500)

Self-documenting names; one thing per function; low cognitive complexity (nesting ≤3); extract a helper only on ≥2 repeats or cross-responsibility reuse; comments explain why/constraints/failure-modes, never narrate. No over-engineering / no demo residue (YAGNI). Delivery docstrings are plain PEP 257 / Google / NumPy style (not markdown), restrained like CVPR-grade open-source; delivery code (`src/**` + delivered scripts + configs) must NOT embed spec/plan/phase/batch/ADR/dev-process pointers — those live in docs, not shipped code. Layering: one-directional downward dependencies, separation of concerns, ADR for contract/architectural changes.

## 5. Verify before claiming done; commit per topic

Run real verification commands before saying "done/passing". Commit only the current topic's files by explicit path. On Windows/PowerShell, keep `git commit -m` messages free of literal double-quotes (they break arg parsing) or use `git commit -F <file>`.

## Make this always-on (optional, recommended)

A skill is pull-based. For a guaranteed per-turn gate:
- Cursor: paste sections 1-2 into Settings → Rules (User Rules).
- OpenCode: put them in `~/.config/opencode/AGENTS.md` (global, always loaded).
