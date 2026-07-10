---
name: parallel-dispatch
description: Decide parallel vs serial subagent decomposition, apply role-based model routing, cap context/output, and set a circuit breaker. Use when a task splits into multiple subtasks or before dispatching implementation/review subagents.
---

# Parallel / Serial Dispatch + Model Routing

## Parallel vs serial

- Parallel ONLY when subtasks are truly independent: disjoint files/modules, no shared mutable state, no ordering dependency, and each has a self-checkable acceptance criterion. Good: independent backend/frontend areas, unrelated services, adversarial/coverage-style multi-answer exploration.
- Serial (default) when there is a shared contract/interface, a producer→consumer chain, or a merge risk. Ordinary single-feature/bugfix work is one coherent worker, NOT many siblings.
- Before parallelizing, compute whether it is worth it (parallel multiplies token cost); if not clearly independent, keep one worker (it may split internally).
- After parallel workers return, the main agent merges, checks for write conflicts / interface drift, and runs integrated verification before accepting.

## Role-based model routing (single source = `config/model-routing.md`)

- Routing is by ROLE, not hardcoded here. `config/model-routing.md` is the source of truth; OpenCode renders the role policy in `opencode/agents/{build,reason,review}.md` from user-supplied provider/model IDs without editing the user's main config.
- Implementation / refactor / debugging / normal architecture → Terra: `gpt-5.6-terra-xhigh`.
- Genuinely complex or difficult design and diagnosis requiring deep reasoning → Sol: `gpt-5.6-sol-xhigh`. Escalate only for a non-obvious cross-system trade-off, an uncertain root cause, or a contract-level decision requiring multi-step reasoning.
- Review / verification → GLM: `glm-5.2-max`, a DIFFERENT model family from both Terra and Sol. No same-family self-verification.
- When dispatching subagents: pass Terra for routine build tasks, Sol for qualifying deep-reasoning work, and GLM for review or verification. OpenCode exposes build/reason/review agents; select its exact installed IDs and choose a genuinely different provider/model family for review.
- Quality first, cost is secondary: avoid unnecessary Sol escalation, keep the fan-out bounded, and do not duplicate research or re-runs.

## Context budget + circuit breaker

- Progressive disclosure: give a subagent the minimal file set + let it glob/grep on demand; do not dump the whole repo.
- Cap a single subagent's output (~25k tokens); summarize rather than paste huge blobs back to main.
- Circuit breaker: set a per-subagent turn/step ceiling; if it loops, thrashes, or drifts off-scope, stop it and re-scope — do not let it run away.
