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
- Unnamed OpenCode Markdown agents inherit the session model. The migration removes `model:` frontmatter from Markdown agents and retires only marker-and-hash verified bundle role-agent Markdown files from discovery; users must manually rename or migrate a custom same-name role agent.
- Before every native dispatch, use the installed `dispatch_resolver.py`, validate an exposed model registry, pass its exact native arguments, and retain the evidence receipt.

## Cursor review and telemetry boundary

Cursor review dispatch uses the binding-selected model with native `generalPurpose`; it never routes review through built-in `explore`. A reviewer is read-only by workflow contract and must not write files, but this bundle does not claim that the native Cursor dispatch API enforces read-only permissions. The parent supplies that contract in the review capsule and remains the only integration authority.

An `actual_model` receipt is valid only when Cursor SDK telemetry explicitly identifies `run.model` or `result.model`. Record the corresponding `actual_model_source` as `cursor-sdk.run.model` or `cursor-sdk.result.model`; do not accept CLI `--actual-model`, UI labels, or a subagent's self-report as runtime evidence. Without one of those SDK sources, retain `actual_model: null`, `cross_model: "unverified"`, and `review_kind: "independent-review-unverified"` for a review. Binding family labels may classify a telemetry-verified requested model, but never manufacture runtime-model evidence.

## Cost strategy

Quality first, cost secondary: avoid unnecessary `reason` escalation and duplicate fan-out.
