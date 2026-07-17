# Independent Code Review

Use the `review` role independently from implementation. Mark findings as blocking or non-blocking and review in this order:

1. Correctness and design, including boundary conditions, state, ordering, and contract integrity.
2. Tests, including failure paths and evidence that new tests failed before implementation.
3. Security and robustness: validate external input, protect secrets, fail loudly, and avoid partial mutation.
4. Compatibility of public APIs, schemas, snapshots, generated artifacts, ownership, and rollback.
5. Readability and architecture: focused responsibilities, low nesting, clear names, useful comments, and no unrequested abstractions.
6. Generated-code risks: placeholders, demo residue, unused imports, duplicated policy prose, or stale references.

For security, concurrency, performance, deployment, or data-loss risk, actively test malformed, empty, oversized, repeated, and interrupted operations. A negative claim such as “unused,” “untested,” or “safe to delete” requires a full-tree or direct-file recheck before acceptance.

The parent verifies blocking findings against the real diff and reruns the decisive checks. Review does not authorize editing outside the requested scope.

## Review-feedback triage

Treat review feedback as evidence to classify, not an automatic edit order. For each finding, classify it as blocking, non-blocking, invalid, or requiring a user decision; cite the affected contract and decisive evidence. Independently reproduce every blocking claim against the current diff before changing code, especially a negative claim about coverage, references, or deletion safety.

For accepted findings, add or update the focused regression test first, make the smallest scoped correction, rerun the decisive checks, and request re-review when a blocking contract changed. Preserve a short disposition for rejected findings so the handoff explains why no edit was made. Escalate ambiguous product, compatibility, or destructive decisions to the user instead of guessing.
