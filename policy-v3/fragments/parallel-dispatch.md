# Parallel Dispatch

Default to one coherent worker. Dispatch siblings in parallel only when their allowed files are disjoint, they share no mutable contract or generated snapshot, neither depends on another's output, and each has an independent acceptance command. Otherwise execute serially.

Before dispatch, load `P07` and create one 300–800 token capsule per worker. Include only the minimum entry points and artifact pointers; let workers inspect more context on demand. Use `build` for implementation, `reason` only for a non-obvious trade-off or unknown root cause, and `review` for independent verification.

Bound fan-out, output size, and retry count. Stop a worker that repeats failed fixes, drifts outside scope, or cannot verify its result. After intake, the parent checks file and contract conflicts, inspects the combined diff, and runs integrated verification.
