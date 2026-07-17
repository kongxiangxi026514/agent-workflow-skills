"""Render deterministic policy-v3 artifacts with source provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping


DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def _canonical_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    outputs = {}
    for policy in registry["policies"]:
        body = _canonical_text(root / policy["source"])
        outputs[Path(policy["artifact"])] = _render_policy(policy, body, registry_hash)
    return outputs


def detect_drift(root: Path | str, expected: Mapping[Path, str]) -> list[str]:
    """Return missing or byte-different generated artifact paths."""
    root = Path(root)
    drift = []
    for relative, content in expected.items():
        target = root / relative
        if not target.is_file() or target.read_bytes() != content.encode("utf-8"):
            drift.append(relative.as_posix())
    return sorted(drift)


def write_outputs(root: Path | str, expected: Mapping[Path, str]) -> None:
    """Write generated artifacts as UTF-8 without BOM and with LF endings."""
    root = Path(root)
    for relative, content in expected.items():
        target = root / relative
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
