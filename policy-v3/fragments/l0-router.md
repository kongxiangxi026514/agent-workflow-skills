# Workflow Risk Router

Route every request before loading detailed policy. Use only this registry's patterns and policy IDs; do not infer a platform model identifier.

## Risk levels

- **R0 Lean**: answers, read-only inspection, or a small low-risk edit. The main agent acts directly and performs a light targeted check.
- **R1 Standard**: ordinary implementation or multi-file work. Load `P01`, use at most one build worker, run targeted tests, and have the parent inspect the diff.
- **R2 Strict**: security, persistent schema, CRS or geometry, training or ground-truth semantics, production deployment, destructive operations, or data-loss risk. Load `P01` and `P04`; add `P06` only for a genuinely hard or ambiguous decision.

Dedicated triggers are deterministic. External documentation or research loads `P02`. A persistent-memory or continual-learning request loads only `P03` and cannot directly write the memory file. Review requests load `P04`. Independent parallel work loads `P05` and its `P07` capsule contract.

User overrides are bounded. A strict/full-process request upgrades to R2. A quick/minimal request may lower ordinary R1 work to R0, but it never suppresses a dedicated research, memory, review, or high-risk trigger. If classification is uncertain, upgrade exactly one risk level.

Do not announce routing on routine turns. Emit a short receipt only when risk escalates, scope changes, a human decision is required, or destructive work is proposed: `risk=R2; loaded=P01,P04; verify=independent-review`.

Workers receive a 300–800 token capsule containing goal, non-goals, risk, allowed and forbidden scope, acceptance, loaded policy IDs, and artifact pointers. Never paste the full workflow into a worker prompt.

Use the portable roles `build`, `reason`, and `review`; resolve their concrete bindings outside policy text. Before every worker dispatch, run the installed `dispatch_resolver.py`, validate an exposed registry, and pass its exact native arguments. Keep the evidence receipt; an unobservable runtime model stays `unverified`. The parent owns scope, integration, and final verification.
