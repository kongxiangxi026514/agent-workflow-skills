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

## Cost strategy

Quality first, cost secondary: avoid unnecessary `reason` escalation and duplicate fan-out.
