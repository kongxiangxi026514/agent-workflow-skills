---
name: parallel-dispatch
description: "Choose serial or parallel workers and enforce bounded task capsules."
---
<!-- GENERATED; policy_id=P05; source=policy-v3/fragments/parallel-dispatch.md; source_sha256=8f012f9dcfd122ac59b16cb3698540baa41f38ffe1b601cf7a785fb696166d44; registry_sha256=a0f339fcdd0ef7577e2f20f614ca1a2c3408ca5591f3bd3690710a9b3963e1a9 -->

# Parallel Dispatch

Default to one coherent worker. Dispatch siblings in parallel only when their allowed files are disjoint, they share no mutable contract or generated snapshot, neither depends on another's output, and each has an independent acceptance command. Otherwise execute serially.

Before dispatch, load `P07` and create one 300–800 token capsule per worker. Include only the minimum entry points and artifact pointers; let workers inspect more context on demand. Use `build` for implementation, `reason` only for a non-obvious trade-off or unknown root cause, and `review` for independent verification.

Before every native subagent dispatch, run the installed `dispatch_resolver.py` with the selected role and the active platform binding. When the platform exposes a model registry, supply the complete list and fail if `requested_model` is unavailable. Pass the resolver's exact native dispatch fields; never permit a silent fallback. Record `role`, `requested_model`, `actual_model` when observable, and `cross_model`. An unobservable runtime model means `cross_model=unverified`; an observed mismatch is an error. Call review cross-model only when family evidence proves separation. Same-family review is independent-context review.

Bound fan-out, output size, and retry count. Stop a worker that repeats failed fixes, drifts outside scope, or cannot verify its result. After intake, the parent checks file and contract conflicts, inspects the combined diff, and runs integrated verification.
