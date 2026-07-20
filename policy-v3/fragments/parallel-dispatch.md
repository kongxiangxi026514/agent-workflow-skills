# Parallel Dispatch

Default to one coherent worker. Dispatch siblings in parallel only when their allowed files are disjoint, they share no mutable contract or generated snapshot, neither depends on another's output, and each has an independent acceptance command. Otherwise execute serially.

Before dispatch, load `P07` and create one 300–800 token capsule per worker. Include only the minimum entry points and artifact pointers; let workers inspect more context on demand. Use `build` for implementation, `reason` only for a non-obvious trade-off or unknown root cause, and `review` for independent verification.

Before every native subagent dispatch, run the installed `dispatch_resolver.py` with the selected role and the active platform binding. When the platform exposes a model registry, supply the complete list and fail if `requested_model` is unavailable. Pass the resolver's exact native dispatch fields; never permit a silent fallback. Cursor review resolves to model-configurable `generalPurpose`, never built-in `explore`, with the exact model from the binding.

Reviewers have a read-only contract: inspect, verify, and report without writing files. The native Cursor dispatch arguments used here have no platform-enforced read-only permission, so include the contract in the review capsule and keep integration with the parent.

Record `role`, `requested_model`, `actual_model`, `actual_model_source`, and `cross_model`. No current SDK adapter is shipped because official SDK telemetry field support is not established. The installed resolver accepts no actual-model or source argument and always records `actual_model=null`, `actual_model_source=null`, `cross_model=unverified`, and `review_kind=independent-review-unverified` for review; binding family labels cannot change that result.

A future adapter must parse a genuine SDK run/result object in a controlled runtime, not CLI input. Until then, CLI values, UI labels, self-reports, and generic library callers must not create runtime-model or cross-model claims.

Bound fan-out, output size, and retry count. Stop a worker that repeats failed fixes, drifts outside scope, or cannot verify its result. After intake, the parent checks file and contract conflicts, inspects the combined diff, and runs integrated verification.
