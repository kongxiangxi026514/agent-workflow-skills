# Workflow Lifecycle

Use this policy for R1 and R2 implementation. Keep the main agent responsible for scope, sequencing, integration, and the final evidence-backed conclusion.

1. **Clarify**: ask only questions whose answers materially change behavior, safety, or compatibility. For fuzzy work, identify the decision, constraints, and non-goals before editing.
2. **Discover**: inspect existing helpers, call chains, public contracts, tests, defaults, and forbidden files. External evidence follows `P02`.
3. **Plan**: define one bounded batch with acceptance checks, a changed-line budget, and a dependency order. Use `P05` only when tasks are genuinely independent.
4. **TDD**: write a focused failing test, confirm the expected failure, implement the minimum behavior, then rerun focused and relevant regression tests.
5. **Accept**: inspect the actual diff, run declared checks, and verify generated or serialized contracts. R2 requires independent review through `P04`.
6. **Close**: report decisions, evidence, residual risk, temporary-artifact disposition, and commit or push state.

Do not turn a narrow task into adjacent cleanup. Stop for a missing destructive choice, a definitive permission failure, or repeated verification failures. Preserve safe existing installer, binding, ownership, and rollback behavior unless the task explicitly changes those contracts.
