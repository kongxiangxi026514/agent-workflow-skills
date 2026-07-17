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


def _canonical_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    parser.add_argument("--check", action="store_true", help="Fail when committed artifacts drift.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary.")
    args = parser.parse_args()
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
