"""Render a provenance-pinned project policy extension from portable v3."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence


REGISTRY_PATH = Path("policy-v3/registry.json")
OVERLAY_PATH = Path("workflow-policy/overlay.json")
POLICY_ROOT = Path("workflow-policy")
GENERATED_ROOT = POLICY_ROOT / "generated"
PORTABLE_IDS = {f"P0{index}" for index in range(8)}
REQUIRED_FIELDS = {
    "policy_id",
    "name",
    "tier",
    "description",
    "trigger",
    "path_selectors",
    "risk",
    "budget_tokens",
    "source",
    "artifact",
    "on_demand",
}
ROUTE_FIELDS = {"route_id", "base_policy_id", "description", "source", "artifact", "budget_tokens"}


def _canonical_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_proxy(text: str) -> int:
    return (len(text) + 3) // 4


def _contained(root: Path, reference: str, allowed_root: Path) -> Path:
    """Resolve one relative reference only when it remains under allowed_root."""
    candidate = Path(reference)
    if candidate.is_absolute() or candidate.anchor:
        raise ValueError(f"absolute path is forbidden: {reference}")
    allowed = (root / allowed_root).resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as error:
        raise ValueError(f"path escapes {allowed_root.as_posix()}: {reference}") from error
    return resolved


def load_extension(project_root: Path | str) -> dict:
    """Load the project's declared v3 extension registry."""
    project_root = Path(project_root)
    return json.loads(_canonical_text(project_root / OVERLAY_PATH))


def _portable_registry(portable_root: Path) -> tuple[dict, str]:
    text = _canonical_text(portable_root / REGISTRY_PATH)
    return json.loads(text), _sha256(text)


def _validate_patterns(label: str, patterns: Iterable[str], errors: list[str]) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except (TypeError, re.error) as error:
            errors.append(f"{label}: invalid selector {pattern!r}: {error}")


def _validate_policy(project_root: Path, policy: dict, errors: list[str]) -> None:
    """Validate one project policy's source, generated destination, and selectors."""
    policy_id = policy.get("policy_id", "?")
    missing = REQUIRED_FIELDS - policy.keys()
    if missing:
        errors.append(f"{policy_id}: missing fields {sorted(missing)}")
        return
    if not re.fullmatch(r"P2\d+", policy_id):
        errors.append(f"{policy_id}: project policy IDs must match P2N")
    if policy["tier"] not in {"L2", "L3"}:
        errors.append(f"{policy_id}: project tier must be L2 or L3")
    if not policy["on_demand"]:
        errors.append(f"{policy_id}: project policy must remain on demand")
    try:
        source = _contained(project_root, policy["source"], POLICY_ROOT)
        _contained(project_root, policy["artifact"], GENERATED_ROOT)
    except ValueError as error:
        errors.append(f"{policy_id}: {error}")
        return
    if not source.is_file():
        errors.append(f"{policy_id}: missing source {policy['source']}")
    if not isinstance(policy["budget_tokens"], int) or not 0 < policy["budget_tokens"] <= 3000:
        errors.append(f"{policy_id}: budget_tokens must be in 1..3000")
    trigger = policy["trigger"]
    if not isinstance(trigger, dict):
        errors.append(f"{policy_id}: trigger must be an object")
        return
    _validate_patterns(f"{policy_id}.trigger.any", trigger.get("any", []), errors)
    _validate_patterns(f"{policy_id}.trigger.none", trigger.get("none", []), errors)
    _validate_patterns(f"{policy_id}.path_selectors", policy["path_selectors"], errors)
    for glob in policy.get("cursor_globs", []):
        if not isinstance(glob, str) or not glob or ".." in Path(glob).parts:
            errors.append(f"{policy_id}: invalid cursor glob {glob!r}")


def _validate_route(project_root: Path, route: dict, errors: list[str]) -> None:
    """Validate one base-policy route that carries project-only operating rules."""
    route_id = route.get("route_id", "?")
    missing = ROUTE_FIELDS - route.keys()
    if missing:
        errors.append(f"{route_id}: missing route fields {sorted(missing)}")
        return
    if route["base_policy_id"] not in {"P01", "P02", "P03", "P04", "P05"}:
        errors.append(f"{route_id}: base_policy_id must be P01 through P05")
    try:
        source = _contained(project_root, route["source"], POLICY_ROOT)
        artifact = _contained(project_root, route["artifact"], GENERATED_ROOT)
    except ValueError as error:
        errors.append(f"{route_id}: {error}")
        return
    if not source.is_file():
        errors.append(f"{route_id}: missing route source {route['source']}")
    if artifact.name != "SKILL.md":
        errors.append(f"{route_id}: route artifact must be a SKILL.md file")
    if not isinstance(route["budget_tokens"], int) or not 0 < route["budget_tokens"] <= 3000:
        errors.append(f"{route_id}: budget_tokens must be in 1..3000")
    if source.is_file() and _token_proxy(_canonical_text(source)) > route["budget_tokens"]:
        errors.append(f"{route_id}: route source exceeds budget")


def _duplicate_identity_errors(overlay: dict) -> list[str]:
    """Return identity collisions before routing or rendering can compress entries."""
    policies = overlay.get("policies", [])
    routes = overlay.get("routes", [])
    policy_ids = [policy.get("policy_id") for policy in policies]
    route_ids = [route.get("route_id") for route in routes]
    errors = []
    if len(policy_ids) != len(set(policy_ids)):
        errors.append("duplicate project policy_id")
    if len(route_ids) != len(set(route_ids)):
        errors.append("duplicate project route_id")
    return errors


def validate_extension(portable_root: Path | str, project_root: Path | str) -> dict:
    """Return extension pin, schema, source, budget, and selector validation errors."""
    portable_root = Path(portable_root)
    project_root = Path(project_root)
    overlay = load_extension(project_root)
    registry, registry_sha256 = _portable_registry(portable_root)
    errors = _duplicate_identity_errors(overlay)
    if overlay.get("schema_version") != registry.get("schema_version"):
        errors.append("schema_version must match the portable registry")
    base = overlay.get("base_registry", {})
    if set(base.get("policy_ids", [])) != PORTABLE_IDS:
        errors.append("base_registry policy_ids must lock P00..P07")
    if not re.fullmatch(r"[0-9a-f]{40}", base.get("revision", "")):
        errors.append("base_registry revision must be a full commit hash")
    if base.get("registry_sha256") != registry_sha256:
        errors.append("base_registry registry_sha256 does not match portable registry")
    policies = overlay.get("policies", [])
    for policy in policies:
        _validate_policy(project_root, policy, errors)
        source = project_root / policy.get("source", "")
        if source.is_file() and _token_proxy(_canonical_text(source)) > policy.get("budget_tokens", 0):
            errors.append(f"{policy.get('policy_id', '?')}: source exceeds budget")
    routes = overlay.get("routes", [])
    for route in routes:
        _validate_route(project_root, route, errors)
    return {"errors": errors, "registry_sha256": registry_sha256}


def _matches(patterns: Iterable[str], value: str) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def select_extension_policy_ids(overlay: dict, task: str, paths: Sequence[str]) -> list[str]:
    """Select extension policies deterministically from task and normalized paths."""
    identity_errors = _duplicate_identity_errors(overlay)
    if identity_errors:
        raise ValueError("; ".join(identity_errors))
    normalized_paths = [path.replace("\\", "/") for path in paths]
    selected = []
    for policy in overlay.get("policies", []):
        trigger = policy["trigger"]
        task_matches = _matches(trigger.get("any", []), task) and not _matches(trigger.get("none", []), task)
        path_matches = any(_matches(policy["path_selectors"], path) for path in normalized_paths)
        if task_matches or path_matches:
            selected.append(policy["policy_id"])
    return sorted(selected)


def _provenance(policy: dict, body: str, base_hash: str, extension_hash: str) -> str:
    return (
        f"<!-- GENERATED; policy_id={policy['policy_id']}; source={policy['source']}; "
        f"source_sha256={_sha256(body)}; base_registry_sha256={base_hash}; "
        f"project_extension_sha256={extension_hash} -->"
    )


def _render_policy(policy: dict, body: str, base_hash: str, extension_hash: str) -> str:
    provenance = _provenance(policy, body, base_hash, extension_hash)
    if policy["artifact"].endswith(".mdc"):
        globs = policy.get("cursor_globs", [])
        glob_lines = "\n".join(f"  - {glob}" for glob in globs)
        frontmatter = f"---\ndescription: {policy['description']}\nglobs:\n{glob_lines}\nalwaysApply: false\n---\n"
        return f"{frontmatter}{provenance}\n\n{body}"
    return f"{provenance}\n\n{body}"


def _render_router(overlay: dict, base_hash: str, extension_hash: str, manifest_hash: str) -> str:
    lines = [
        "---",
        "description: Generated v3 project extension router.",
        "alwaysApply: true",
        "---",
        "<!-- Managed by agent-workflow-skills project extension. -->",
        (
            "<!-- GENERATED; policy_id=project-extension-router; "
            f"base_registry_sha256={base_hash}; project_extension_sha256={extension_hash}; "
            f"manifest_sha256={manifest_hash} -->"
        ),
        "",
        "# Project Extension Router",
        "",
        "Use `workflow-policy/generated/manifest.json` to select project policies.",
        "Load only selected L2/L3 sources; do not treat them as fixed context.",
    ]
    for policy in sorted(overlay["policies"], key=lambda item: item["policy_id"]):
        lines.append(f"- {policy['policy_id']}: `{policy['source']}`")
    for route in sorted(overlay.get("routes", []), key=lambda item: item["route_id"]):
        lines.append(f"- {route['base_policy_id']} route `{route['route_id']}`: `{route['source']}`")
    return "\n".join(lines) + "\n"


def _render_route(route: dict, body: str, base_hash: str, extension_hash: str) -> str:
    provenance = (
        f"<!-- GENERATED; route_id={route['route_id']}; base_policy_id={route['base_policy_id']}; "
        f"source={route['source']}; source_sha256={_sha256(body)}; "
        f"base_registry_sha256={base_hash}; project_extension_sha256={extension_hash} -->"
    )
    frontmatter = (
        "---\n"
        f"name: project-{route['route_id']}\n"
        f"description: {json.dumps(route['description'], ensure_ascii=False)}\n"
        "---\n"
    )
    return f"{frontmatter}{provenance}\n\n{body}"


def _render_manifest(
    overlay: dict,
    base_hash: str,
    extension_hash: str,
    project_root: Path,
    artifact_outputs: Mapping[Path, str],
) -> str:
    policies = []
    for policy in sorted(overlay["policies"], key=lambda item: item["policy_id"]):
        body = _canonical_text(project_root / policy["source"])
        policies.append(
            {
                "artifact": policy["artifact"],
                "artifact_sha256": _sha256(artifact_outputs[Path(policy["artifact"])]),
                "policy_id": policy["policy_id"],
                "source": policy["source"],
                "source_sha256": _sha256(body),
                "task_selectors": policy["trigger"],
                "path_selectors": policy["path_selectors"],
            }
        )
    manifest = {
        "base_registry_sha256": base_hash,
        "project_extension_sha256": extension_hash,
        "policies": policies,
        "routes": [
            {
                "artifact": route["artifact"],
                "artifact_sha256": _sha256(artifact_outputs[Path(route["artifact"])]),
                "base_policy_id": route["base_policy_id"],
                "route_id": route["route_id"],
                "source": route["source"],
                "source_sha256": _sha256(_canonical_text(project_root / route["source"])),
            }
            for route in sorted(overlay.get("routes", []), key=lambda item: item["route_id"])
        ],
        "schema_version": "1.0",
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def expected_extension_outputs(portable_root: Path | str, project_root: Path | str) -> dict[Path, str]:
    """Return every deterministic output after enforcing the extension contract."""
    portable_root = Path(portable_root)
    project_root = Path(project_root)
    report = validate_extension(portable_root, project_root)
    if report["errors"]:
        raise ValueError("; ".join(report["errors"]))
    overlay_path = project_root / OVERLAY_PATH
    extension_hash = _sha256(_canonical_text(overlay_path))
    base_hash = report["registry_sha256"]
    overlay = load_extension(project_root)
    outputs = {
        Path(policy["artifact"]): _render_policy(
            policy,
            _canonical_text(project_root / policy["source"]),
            base_hash,
            extension_hash,
        )
        for policy in overlay["policies"]
    }
    outputs.update(
        {
            Path(route["artifact"]): _render_route(
                route,
                _canonical_text(project_root / route["source"]),
                base_hash,
                extension_hash,
            )
            for route in overlay.get("routes", [])
        }
    )
    manifest = _render_manifest(overlay, base_hash, extension_hash, project_root, outputs)
    outputs[GENERATED_ROOT / "manifest.json"] = manifest
    outputs[GENERATED_ROOT / "cursor/project-extension-router.mdc"] = _render_router(
        overlay, base_hash, extension_hash, _sha256(manifest)
    )
    return outputs


def detect_extension_drift(project_root: Path | str, expected: Mapping[Path, str]) -> list[str]:
    """Return generated project-extension artifacts that are missing or stale."""
    project_root = Path(project_root)
    return sorted(
        relative.as_posix()
        for relative, content in expected.items()
        if not (project_root / relative).is_file()
        or (project_root / relative).read_bytes() != content.encode("utf-8")
    )


def write_extension_outputs(project_root: Path | str, expected: Mapping[Path, str]) -> None:
    """Write extension artifacts only below workflow-policy/generated."""
    project_root = Path(project_root)
    for relative, content in expected.items():
        target = _contained(project_root, relative.as_posix(), GENERATED_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
