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

## Role-based model routing (identity is the single knob, not hardcoded slugs)

- Implement / refactor / debug → the strong implementer model (this workspace: `claude-opus-4-8-thinking-xhigh`, or `…-max` for hard tasks; OpenCode: `agent.build.model`).
- Review / verification → a DIFFERENT model family (this workspace: `gpt-5.5-extra-high`; OpenCode: `agent.review.model`). No same-model self-verification.
- Quality first, cost is secondary — but actively manage cost/time: pick the cheapest model that meets the quality bar for mechanical work, reserve top models for design/review/verification.

## Context budget + circuit breaker

- Progressive disclosure: give a subagent the minimal file set + let it glob/grep on demand; do not dump the whole repo.
- Cap a single subagent's output (~25k tokens); summarize rather than paste huge blobs back to main.
- Circuit breaker: set a per-subagent turn/step ceiling; if it loops, thrashes, or drifts off-scope, stop it and re-scope — do not let it run away.
