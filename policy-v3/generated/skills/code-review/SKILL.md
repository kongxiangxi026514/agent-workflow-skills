---
name: code-review
description: "Independent layered review with adversarial checks for high-risk changes."
---
<!-- GENERATED; policy_id=P04; source=policy-v3/fragments/code-review.md; source_sha256=2f508dbbdc4cb75eff51eaa118715f7bba416a7e19435aeb2404fd38af38beba; registry_sha256=774f226f2600847405f2d0c038583e051108693286dad5a72490d793332a10ec -->

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
