# Model Routing

Portable policy defines roles only; each installation keeps concrete IDs in its user-editable `model-routing.jsonc`, and an explicitly migrated OpenCode host mirrors its role IDs in the selected native JSON/JSONC role map.

## Hard rules

- `build`: implementation, refactor, debugging, and normal architecture.
- `reason`: qualifying difficult reasoning only; null reuses `build`.
- `review`: independent verification with an ID different from `build` and effective `reason`.
- The installer enforces ID inequality. It cannot infer model-family independence from arbitrary provider strings.
- Optional `families` labels are operator-supplied evidence; never infer them from IDs.
- Cursor and OpenCode bindings are separate. An `all` install rejects generic model options that could cross the platform boundary.
- Cursor resolves IDs only from its machine-local JSONC binding. OpenCode resolves its native role IDs from the selected JSON/JSONC `agent.build`, `agent.reason`, and `agent.review` entries after an explicit audited migration.
- Unnamed OpenCode Markdown agents retain their own frontmatter and configuration. The migration retires only marker-and-hash verified bundle role-agent Markdown files from discovery; users must manually rename or migrate a custom same-name role agent.
- OpenCode `reason` and `review` are fail-closed read-only roles: unknown tools, edit, bash, task and external-directory access are denied. Provide `-AvailableOpenCodeModel` / `--available-opencode-model` when a runtime registry is available; every build/effective-reason/review ID must be present or installation fails without fallback.
- Before every native dispatch, use the installed `dispatch_resolver.py`, validate an exposed model registry, pass its exact native arguments, and retain the evidence receipt.

## Cursor review and telemetry boundary

Cursor review dispatch uses the binding-selected model with native `generalPurpose`; it never routes review through built-in `explore`. A reviewer is read-only by workflow contract and must not write files, but this bundle does not claim that the native Cursor dispatch API enforces read-only permissions. The parent supplies that contract in the review capsule and remains the only integration authority.

No current SDK adapter is shipped because official SDK telemetry field support is not established. The installed resolver has no actual-model or source input path and always emits `actual_model: null`, `actual_model_source: null`, `cross_model: "unverified"`, and `review_kind: "independent-review-unverified"` for review. Binding family labels cannot manufacture runtime-model evidence or a cross-model result.

A future adapter must parse a genuine SDK run/result object in a controlled runtime, not CLI input. Until that adapter exists, CLI values, UI labels, self-reports, and generic library callers must not create runtime-model or cross-model claims.

## Cost strategy

Quality first, cost secondary: avoid unnecessary `reason` escalation and duplicate fan-out.
