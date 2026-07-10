# Model Routing (single source of truth)

This file is the **only** source for Cursor role slugs. OpenCode model IDs are selected at install time because provider/model IDs are local to the user's OpenCode installation.

## Role → model

| Role | Responsibility | Cursor slug | OpenCode native agent |
| --- | --- | --- | --- |
| implementer | Implementation, refactor, debugging, and normal architecture work | `gpt-5.6-terra-xhigh` | `build.md` |
| reasoner | Genuinely complex or difficult design and diagnosis that require deep reasoning | `gpt-5.6-sol-xhigh` | `reason.md` |
| reviewer | Review and verification | `glm-5.2-max` | `review.md` |

## Hard rules

- Use Terra by default for implementation, refactoring, debugging, and normal architecture work.
- Escalate to Sol only when a design or diagnosis remains genuinely difficult after ordinary analysis: a non-obvious cross-system trade-off, an uncertain root cause, or a contract-level decision requiring deep multi-step reasoning.
- **The reviewer MUST be a different model family from both the implementer and reasoner**, to avoid same-family self-verification blind spots.
- Non-trivial changes: implementer or reasoner completes the work → reviewer performs a cross-model review → main agent independently re-verifies. Contract-level (D-risk) changes MUST complete all three steps and never accept self-approval as the final conclusion.

## Switching models

- **Cursor**: edit the "Role → model" table in this file, then sync the same slugs and roles in `rules/workflow-gate.mdc` and `skills/parallel-dispatch/SKILL.md`. Dispatch Terra for routine implementation work, Sol for qualifying complex design or diagnosis, and GLM for review or verification.
- **OpenCode**: `opencode/agents/{build,reason,review}.md` contain a `model:` placeholder. The installer renders it from the user's exact available provider/model IDs; it never maps Cursor slugs or modifies `opencode.json` / `opencode.jsonc`. Run `opencode models`, supply all three IDs, and choose a genuinely different provider/model family for review. String inequality is enforced, but cannot prove family separation.

## Cost strategy

Quality first, cost secondary but **actively managed**: follow the explicit role mapping above, avoid unnecessary Sol escalation, control the number of subagents and parallel fan-out, and avoid duplicate research or re-runs.
