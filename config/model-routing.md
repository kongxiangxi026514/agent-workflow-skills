# Model Routing (single source of truth)

This file is the **only** place to edit for defining "which role uses which model". Change it here, and the workflow spine and each tool's model routing follow.

## Role → model

| Role | Responsibility | Cursor slug |
| --- | --- | --- |
| implementer | Implementation / refactor / debug | `claude-opus-4-8-thinking-xhigh` (escalate hard tasks → `claude-opus-4-8-thinking-max`) |
| reviewer | Review / verification | `gpt-5.5-extra-high` |

## Hard rules

- **The reviewer MUST be a different model family from the implementer**, to avoid the blind spot of same-model self-verification (cross-model verification).
- Non-trivial changes: implementer implements → reviewer does a cross-model review → main agent independently re-verifies; contract-level (D-risk) changes MUST complete all three steps and never accept the implementer's self-approval as the final conclusion.

## Dynamically switching models (edit here = single point)

- **Cursor**: edit the "Role → model" table in this file, and sync the slugs in the `## Model routing (dynamic single point)` section of `rules/workflow-gate.mdc`. When dispatching subagents, pass the implementer model for build tasks and the reviewer model for review tasks.
- **OpenCode**: edit `agent.build.model` / `agent.review.model` in `opencode/opencode.json`. Look up real available ids with `opencode models` (e.g. build with GLM 5.2, review with Kimi K2.6 — different families).

## Cost strategy

Quality first, cost secondary but **actively managed**: use a cheap, fast, good-enough model for mechanical work (formatting / bulk renames / simple migrations), and reserve strong models for high-value steps like design / review / verification; control the number of subagents and the parallel fan-out, and avoid pointless duplicate research and re-runs.
