---
name: parallel-dispatch
description: "Choose serial or parallel workers and enforce bounded task capsules."
---
<!-- GENERATED; policy_id=P05; source=policy-v3/fragments/parallel-dispatch.md; source_sha256=eb8cfebb1e14ea0e7c188f4d75b66387e56935c2bd47757df36a207b2a1ac631; registry_sha256=7e2c89e18d48d1ac4fc33a9a949952dd26e96af66fe90f6051151f6726172261 -->

# Parallel Dispatch

Default to one coherent worker. Dispatch siblings in parallel only when their allowed files are disjoint, they share no mutable contract or generated snapshot, neither depends on another's output, and each has an independent acceptance command. Otherwise execute serially.

Before dispatch, load `P07` and create one 300–800 token capsule per worker. Include only the minimum entry points and artifact pointers; let workers inspect more context on demand. Use `build` for implementation, `reason` only for a non-obvious trade-off or unknown root cause, and `review` for independent verification.

Bound fan-out, output size, and retry count. Stop a worker that repeats failed fixes, drifts outside scope, or cannot verify its result. After intake, the parent checks file and contract conflicts, inspects the combined diff, and runs integrated verification.
