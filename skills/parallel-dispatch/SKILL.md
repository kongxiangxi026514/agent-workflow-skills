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

## Role-based model routing

- `build`: implementation, refactoring, debugging, and normal architecture.
- `reason`: only non-obvious cross-system trade-offs, uncertain root causes, or contract-level decisions requiring multi-step reasoning.
- `review`: independent review and verification with a different model from `build` and effective `reason`.
- Resolve role IDs from the active tool's machine-local binding. A null `reason` reuses `build`; ID inequality is enforceable, but provider strings do not prove family separation.
- Quality first, cost secondary: avoid unnecessary `reason` escalation, bound fan-out, and avoid duplicate work.

## Context budget + circuit breaker

- Progressive disclosure: give a subagent the minimal file set + let it glob/grep on demand; do not dump the whole repo.
- Cap a single subagent's output (~25k tokens); summarize rather than paste huge blobs back to main.
- Circuit breaker: set a per-subagent turn/step ceiling; if it loops, thrashes, or drifts off-scope, stop it and re-scope — do not let it run away.
