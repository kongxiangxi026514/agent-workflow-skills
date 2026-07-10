# Model Routing (single source of truth)

This file is the **only** place to edit for defining "which role uses which model". Change it here, and the workflow spine and each tool's model routing follow.

## Role → model

| Role | Responsibility | Cursor slug |
| --- | --- | --- |
| implementer | Implementation, refactor, debugging, and normal architecture work | `gpt-5.6-terra-xhigh` |
| reasoner | Genuinely complex or difficult design and diagnosis that require deep reasoning | `gpt-5.6-sol-xhigh` |
| reviewer | Review and verification | `glm-5.2-max` |

## Hard rules

- Use Terra by default for implementation, refactoring, debugging, and normal architecture work.
- Escalate to Sol only when a design or diagnosis remains genuinely difficult after ordinary analysis: a non-obvious cross-system trade-off, an uncertain root cause, or a contract-level decision requiring deep multi-step reasoning.
- **The reviewer MUST be a different model family from both the implementer and reasoner**, to avoid same-family self-verification blind spots.
- Non-trivial changes: implementer or reasoner completes the work → reviewer performs a cross-model review → main agent independently re-verifies. Contract-level (D-risk) changes MUST complete all three steps and never accept self-approval as the final conclusion.

## Dynamically switching models (edit here = single point)

- **Cursor**: edit the "Role → model" table in this file, then sync the same slugs and roles in `rules/workflow-gate.mdc` and `skills/parallel-dispatch/SKILL.md`. Dispatch Terra for routine implementation work, Sol for qualifying complex design or diagnosis, and GLM for review or verification.
- **OpenCode**: `opencode/agents/build.md` and `review.md` express the same roles without changing the user's main config. Build defaults to Terra and escalates qualifying deep reasoning to Sol; review remains different-family GLM.

## Cost strategy

Quality first, cost secondary but **actively managed**: follow the explicit role mapping above, avoid unnecessary Sol escalation, control the number of subagents and parallel fan-out, and avoid duplicate research or re-runs.
