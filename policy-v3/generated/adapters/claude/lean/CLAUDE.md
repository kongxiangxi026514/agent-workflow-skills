<!-- GENERATED; policy_id=P00; source=policy-v3/fragments/l0-router.md; source_sha256=602b34a8f3289eefcc501a40e12eeff8b823c24d4d08ea11979f5a857f725b5f; registry_sha256=57d781f3619d79152b7a501ea52993e677b977bb9c48115e97328a4a2306b5d0; platform=claude; profile=lean; profile_sha256=4daee70a12c80d742bdd80a4fda99ba70077025c9d3bd9a4c061d2b9be4291e2 -->
<!-- profile-settings={"budget":{"capsule_max":600,"l0_max":1100},"escalation":{"ordinary_change_min_paths":2,"ordinary_path_count":3}} -->

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
