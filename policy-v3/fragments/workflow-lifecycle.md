# Workflow Lifecycle

Use this policy for R1 and R2 implementation. Keep the main agent responsible for scope, sequencing, integration, and the final evidence-backed conclusion.

1. **Clarify**: ask only questions whose answers materially change behavior, safety, or compatibility. For fuzzy work, identify the decision, constraints, and non-goals before editing.
2. **Discover**: inspect existing helpers, call chains, public contracts, tests, defaults, and forbidden files. External evidence follows `P02`.
3. **Plan**: define one bounded batch with acceptance checks, a changed-line budget, and a dependency order. Use `P05` only when tasks are genuinely independent.
4. **TDD**: write a focused failing test, confirm the expected failure, implement the minimum behavior, then rerun focused and relevant regression tests.
5. **Accept**: inspect the actual diff, run declared checks, and verify generated or serialized contracts. R2 requires independent review through `P04`.
6. **Close**: report decisions, evidence, residual risk, temporary-artifact disposition, and commit or push state.

Do not turn a narrow task into adjacent cleanup. Stop for a missing destructive choice, a definitive permission failure, or repeated verification failures. Preserve safe existing installer, binding, ownership, and rollback behavior unless the task explicitly changes those contracts.

## R2 formal design gate

For R2 work, an explicit full-process request, or `/grilling`, do not implement immediately. Ask only grill questions that could change safety, compatibility, scope, or the chosen design. Then prepare a concise Chinese-primary design/spec with the objective, non-goals, invariants, risks, acceptance evidence, and 2–3 viable alternatives with a recommendation.

Request explicit user approval of that design/spec before creating an implementation plan or changing code. The approval may be the user's supplied approved plan/spec; otherwise wait for their decision. After approval, derive one bounded plan with dependencies, owner, changed-line budget, and tests. Do not use this gate for an ordinary R0/R1 task unless the user explicitly requests it.

## Grill gate

`/grilling` is the explicit alias for this gate. It preserves grill-me's design challenge without a permanently loaded prompt: ask the material questions, compare alternatives, and wait for approval before implementation.

## Task ledger, checkpoint, and handoff

Use a compact Task ledger only for an R2, multi-session, or explicitly resumable task. It is a task artifact, not always-on memory and not a Trellis runtime dependency. Put it in a user-approved task-artifact location; do not create persistent workspace memory or add a runtime package for it.

- **Objective and decisions**: record the approved goal, non-goals, selected alternative, and unresolved choices.
- **Completed steps and failures**: record each completed bounded step, failed attempt, and its evidence without copying full transcripts.
- **Checkpoint**: after a meaningful verification or blocker, record changed paths, exact commands and outcomes, remaining risk, and the next action.
- **Handoff**: end with a compact summary of task state, required artifacts, constraints, and the next owner action. A successor verifies the cited evidence instead of trusting the ledger blindly.

## Worktree and branch lifecycle

Use this procedure only when the user requests isolation, a branch deliverable, or a change needs reviewable separation. First detect existing worktrees and inspect the selected base revision, branch status, and working-tree cleanliness. Reuse a clean, suitable worktree; otherwise create a dedicated branch from the selected base revision and a clean isolated worktree without modifying unrelated dirty checkouts.

Run the relevant baseline checks before editing. Keep each commit single-topic and within the declared changed-line budget. Before branch finish, inspect the complete diff, rerun declared verification, obtain the required independent review, and state whether the next action is push, merge/PR, retain for handoff, or rollback. Never merge, delete a branch, or push without the user's requested destination.
