"""Verify installed generated policy artifacts before an installer refresh."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BEGIN = "<!-- BEGIN agent-workflow-skills spine -->"
END = "<!-- END agent-workflow-skills spine -->"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spine_body(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError(f"corrupted spine markers: {path}")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0].strip("\r\n")
    return (body + "\n").encode("utf-8")


def _spine_block(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError(f"corrupted spine markers: {path}")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0].strip("\r\n")
    return f"{BEGIN}\n{body}\n{END}".encode("utf-8")


def verify(state_path: Path, adapter_path: Path, skills_dir: Path, spine: bool) -> None:
    """Raise when a previously installed generated policy artifact drifted."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if spine and adapter_path.exists() and BEGIN in adapter_path.read_text(encoding="utf-8"):
        expected_block = state.get("spine_block_sha256")
        if not isinstance(expected_block, str):
            raise ValueError(f"missing managed spine provenance: {state_path}")
        if hashlib.sha256(_spine_block(adapter_path)).hexdigest() != expected_block:
            raise ValueError(f"generated spine drift: {adapter_path}")
    owned = state.get("policy_owned_sha256", {})
    if not owned:
        return
    actual_adapter = _spine_body(adapter_path) if spine else adapter_path.read_bytes()
    if hashlib.sha256(actual_adapter).hexdigest() != owned.get("workflow-gate.mdc"):
        raise ValueError(f"generated policy drift: {adapter_path}")
    for relative, expected in owned.items():
        if relative == "workflow-gate.mdc":
            continue
        skill_relative = relative[len("skills/"):]
        if _hash(skills_dir / skill_relative) != expected:
            raise ValueError(f"generated policy drift: {skills_dir / skill_relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--spine", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.state, args.adapter, args.skills, args.spine)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
