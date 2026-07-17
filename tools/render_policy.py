"""Render deterministic policy-v3 artifacts with source provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("policy-v3/fragments")
ARTIFACT_ROOT = Path("policy-v3/generated")
ADAPTER_ROOT = ARTIFACT_ROOT / "adapters"


def _canonical_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def profile_names(root: Path | str = DEFAULT_ROOT) -> tuple[str, ...]:
    """Return supported installer profiles in deterministic order."""
    registry = json.loads(_canonical_text(Path(root) / "policy-v3" / "registry.json"))
    profiles = registry.get("profiles", {})
    if not profiles:
        raise ValueError("registry has no installer profiles")
    return tuple(sorted(profiles))


def profile_settings(root: Path | str, profile: str) -> dict:
    """Return one validated profile plus the invariant strict behavior."""
    registry = json.loads(_canonical_text(Path(root) / "policy-v3" / "registry.json"))
    try:
        settings = registry["profiles"][profile]
    except KeyError as error:
        raise ValueError(f"unknown installer profile: {profile}") from error
    required = {"escalation", "budget"}
    if set(settings) != required:
        raise ValueError(f"profile {profile} must contain only escalation and budget")
    strict = {
        "risk": "R2",
        "risk_auto_load": registry["router"]["risk_auto_load"]["R2"],
    }
    return {**settings, "strict": strict}


def _profile_adapter_path(platform: str, profile: str) -> Path:
    if platform == "cursor":
        return ADAPTER_ROOT / platform / profile / "workflow-gate.mdc"
    if platform == "opencode":
        return ADAPTER_ROOT / platform / profile / "AGENTS.md"
    if platform == "claude":
        return ADAPTER_ROOT / platform / profile / "CLAUDE.md"
    raise ValueError(f"unsupported profile adapter platform: {platform}")


def _resolve_contained_path(
    root: Path,
    reference: str | Path,
    allowed_root: Path,
    field: str,
) -> Path:
    """Resolve a registry path only when it remains under its allowed root."""
    if not isinstance(reference, (str, Path)):
        raise ValueError(f"{field} must be a relative path")
    candidate = Path(reference)
    if candidate.is_absolute() or candidate.anchor:
        raise ValueError(f"{field} must not be absolute: {reference}")
    allowed = (root / allowed_root).resolve()
    target = (root / candidate).resolve()
    try:
        target.relative_to(allowed)
    except ValueError as error:
        raise ValueError(f"{field} resolves outside {allowed_root.as_posix()}: {reference}") from error
    return target


def resolve_policy_paths(root: Path | str, policy: dict) -> tuple[Path, Path]:
    """Resolve one policy's fragment and artifact inside their dedicated roots."""
    root = Path(root)
    source = _resolve_contained_path(root, policy["source"], SOURCE_ROOT, "source")
    artifact = _resolve_contained_path(root, policy["artifact"], ARTIFACT_ROOT, "artifact")
    return source, artifact


def validate_registry_paths(root: Path | str, registry: dict) -> list[str]:
    """Return containment errors without reading fragments or writing artifacts."""
    errors = []
    for policy in registry.get("policies", []):
        policy_id = policy.get("policy_id", "?")
        try:
            resolve_policy_paths(root, policy)
        except (KeyError, ValueError) as error:
            errors.append(f"{policy_id}: {error}")
    return errors


def _render_policy(policy: dict, body: str, registry_hash: str) -> str:
    provenance = (
        f"<!-- GENERATED; policy_id={policy['policy_id']}; source={policy['source']}; "
        f"source_sha256={_sha256(body)}; registry_sha256={registry_hash} -->"
    )
    if policy["artifact"].endswith("/SKILL.md"):
        frontmatter = (
            "---\n"
            f"name: {policy['name']}\n"
            f"description: {json.dumps(policy['description'], ensure_ascii=False)}\n"
            "---\n"
        )
        return f"{frontmatter}{provenance}\n\n{body}"
    return f"{provenance}\n\n{body}"


def expected_profile_adapter(root: Path | str, platform: str, profile: str) -> str:
    """Render one platform adapter from the canonical L0 fragment."""
    root = Path(root)
    registry_text = _canonical_text(root / "policy-v3" / "registry.json")
    registry = json.loads(registry_text)
    settings = profile_settings(root, profile)
    policy = next(item for item in registry["policies"] if item["policy_id"] == "P00")
    source, _ = resolve_policy_paths(root, policy)
    body = _canonical_text(source)
    profile_json = json.dumps(
        {"budget": settings["budget"], "escalation": settings["escalation"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    provenance = (
        f"<!-- GENERATED; policy_id=P00; source={policy['source']}; "
        f"source_sha256={_sha256(body)}; registry_sha256={_sha256(registry_text)}; "
        f"platform={platform}; profile={profile}; profile_sha256={_sha256(profile_json)} -->"
    )
    profile_line = f"<!-- profile-settings={profile_json} -->"
    if platform == "cursor":
        rendered = (
            "---\n"
            f"description: Generated policy-v3 L0 router (profile={profile}).\n"
            "alwaysApply: true\n"
            "---\n"
            "<!-- Managed by agent-workflow-skills. -->\n"
            f"{provenance}\n{profile_line}\n\n{body}"
        )
    elif platform in ("claude", "opencode"):
        rendered = f"{provenance}\n{profile_line}\n\n{body}"
    else:
        raise ValueError(f"unsupported profile adapter platform: {platform}")
    if _token_proxy(rendered) > settings["budget"]["l0_max"]:
        raise ValueError(f"{platform}/{profile} L0 adapter exceeds its profile budget")
    return rendered


def _token_proxy(text: str) -> int:
    return (len(text) + 3) // 4


def profile_adapter_drift(target: Path, expected: str) -> bool:
    """Return whether one installed or committed adapter differs from its source render."""
    return not target.is_file() or target.read_bytes() != expected.encode("utf-8")


def expected_outputs(root: Path | str = DEFAULT_ROOT) -> dict[Path, str]:
    """Build every expected generated artifact in registry order."""
    root = Path(root)
    registry_path = root / "policy-v3" / "registry.json"
    registry_text = _canonical_text(registry_path)
    registry = json.loads(registry_text)
    registry_hash = _sha256(registry_text)
    path_errors = validate_registry_paths(root, registry)
    if path_errors:
        raise ValueError("; ".join(path_errors))
    outputs = {}
    for policy in registry["policies"]:
        source, artifact = resolve_policy_paths(root, policy)
        body = _canonical_text(source)
        outputs[artifact.relative_to(root.resolve())] = _render_policy(policy, body, registry_hash)
    for platform in ("cursor", "opencode", "claude"):
        for profile in profile_names(root):
            relative = _profile_adapter_path(platform, profile)
            outputs[relative] = expected_profile_adapter(root, platform, profile)
    return outputs


def detect_drift(root: Path | str, expected: Mapping[Path, str]) -> list[str]:
    """Return missing or byte-different generated artifact paths."""
    root = Path(root)
    drift = []
    for relative, content in expected.items():
        target = _resolve_contained_path(root, relative, ARTIFACT_ROOT, "artifact")
        if not target.is_file() or target.read_bytes() != content.encode("utf-8"):
            drift.append(relative.as_posix())
    return sorted(drift)


def write_outputs(root: Path | str, expected: Mapping[Path, str]) -> None:
    """Write generated artifacts as UTF-8 without BOM and with LF endings."""
    root = Path(root)
    for relative, content in expected.items():
        target = _resolve_contained_path(root, relative, ARTIFACT_ROOT, "artifact")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Render one provenance-pinned project extension instead of portable artifacts.",
    )
    parser.add_argument("--check", action="store_true", help="Fail when committed artifacts drift.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary.")
    args = parser.parse_args()
    if args.project_root:
        from render_project_extension import (
            detect_extension_drift,
            expected_extension_outputs,
            write_extension_outputs,
        )

        expected = expected_extension_outputs(args.root, args.project_root)
        drift = detect_extension_drift(args.project_root, expected)
        if not args.check:
            write_extension_outputs(args.project_root, expected)
            drift = []
    else:
        expected = expected_outputs(args.root)
        drift = detect_drift(args.root, expected)
        if not args.check:
            write_outputs(args.root, expected)
            drift = []
    report = {"artifacts": len(expected), "drift": drift}
    print(json.dumps(report, sort_keys=True) if args.json else report)
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
