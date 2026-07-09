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

- Routing is by ROLE, not hardcoded here. The single source of truth is `config/model-routing.md` (and, for OpenCode, `opencode.json` `agent.build.model` / `agent.review.model`); change models there.
- Implement / refactor / debug → the **implementer** model (current: `claude-opus-4-8-thinking-xhigh`, escalate hard tasks to `claude-opus-4-8-thinking-max`; OpenCode: `agent.build.model`).
- Review / verification → the **reviewer** model, a DIFFERENT model family (current: `gpt-5.5-extra-high`; OpenCode: `agent.review.model`). No same-model self-verification.
- When dispatching subagents: pass the implementer model for build tasks and the reviewer model for review tasks.
- Quality first, cost is secondary — but actively manage cost/time: pick the cheapest model that meets the quality bar for mechanical work, reserve top models for design/review/verification.

## Context budget + circuit breaker

- Progressive disclosure: give a subagent the minimal file set + let it glob/grep on demand; do not dump the whole repo.
- Cap a single subagent's output (~25k tokens); summarize rather than paste huge blobs back to main.
- Circuit breaker: set a per-subagent turn/step ceiling; if it loops, thrashes, or drifts off-scope, stop it and re-scope — do not let it run away.
