"""Validate Cursor bundle ownership before replacing or removing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_for(relative: str, rules: Path, skills: Path, bundle: Path) -> Path:
    if relative.startswith("skills/"):
        return skills / relative[len("skills/") :]
    if relative in {"workflow-gate.mdc", "model-routing.mdc"}:
        return rules / relative
    return bundle / relative


def verify(state_path: Path, rules: Path, skills: Path, bundle: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("bundle") != "agent-workflow-skills" or state.get("platform") != "cursor":
        raise ValueError(f"invalid Cursor ownership state: {state_path}")
    owned = state.get("owned_sha256")
    if not isinstance(owned, dict) or not owned:
        raise ValueError(f"missing Cursor ownership hashes: {state_path}")
    for relative, expected in owned.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError(f"invalid Cursor ownership entry: {state_path}")
        path = _path_for(relative, rules, skills, bundle)
        if not path.is_file() or _hash(path) != expected:
            raise ValueError(f"Cursor ownership drift: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.state, args.rules, args.skills, args.bundle)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
