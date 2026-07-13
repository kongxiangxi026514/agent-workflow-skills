# Model Routing

Portable policy defines roles only; each installation keeps concrete IDs in its user-editable `model-routing.jsonc`.

## Hard rules

- `build`: implementation, refactor, debugging, and normal architecture.
- `reason`: qualifying difficult reasoning only; null reuses `build`.
- `review`: independent verification with an ID different from `build` and effective `reason`.
- The installer enforces ID inequality. It cannot infer model-family independence from arbitrary provider strings.

## Cost strategy

Quality first, cost secondary: avoid unnecessary `reason` escalation and duplicate fan-out.
