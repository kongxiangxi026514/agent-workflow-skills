"""Validate Cursor bundle ownership before replacing or removing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from dispatch_resolver import DispatchResolutionError, _load_binding


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


MARKER = ".agent-workflow-skills-owned"
MARKER_BYTES = b"agent-workflow-skills\n"
EDITABLE_BINDING = "model-routing.jsonc"


def _project_path_for(relative: str, rules: Path, bundle: Path) -> Path:
    if relative in {"workflow-gate.mdc", "model-routing.mdc"}:
        return rules / relative
    return bundle / relative


def verify_global_skills(skills: Path, source_skills: Path) -> None:
    """Validate globally shared skills against the stable generated source tree."""
    for source in sorted(path for path in source_skills.iterdir() if path.is_dir()):
        destination = skills / source.name
        if not destination.is_dir():
            raise ValueError(f"missing Cursor bundle skill: {destination}")
        expected = {
            path.relative_to(source): path.read_bytes()
            for path in source.rglob("*")
            if path.is_file()
        }
        actual_files = {
            path.relative_to(destination): path
            for path in destination.rglob("*")
            if path.is_file()
        }
        if set(actual_files) != set(expected) | {Path(MARKER)}:
            raise ValueError(f"Cursor skill content drift: {destination}")
        marker = destination / MARKER
        if marker.read_bytes() != MARKER_BYTES:
            raise ValueError(f"Cursor skill marker drift: {marker}")
        for relative, content in expected.items():
            if actual_files[relative].read_bytes() != content:
                raise ValueError(f"Cursor skill content drift: {actual_files[relative]}")


def _verify_editable_binding(path: Path) -> None:
    """Allow a user-edited Cursor binding only when it remains safe and valid."""
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise ValueError(f"missing Cursor model binding: {path}") from error
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or attributes & reparse
    ):
        raise ValueError(f"Cursor model binding must be a regular non-reparse file: {path}")
    try:
        _load_binding("cursor", path)
    except DispatchResolutionError as error:
        raise ValueError(f"invalid Cursor model binding: {error}") from error


def verify_project(state_path: Path, rules: Path, bundle: Path) -> None:
    """Validate artifacts owned only by one Cursor project install state."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("bundle") != "agent-workflow-skills" or state.get("platform") != "cursor":
        raise ValueError(f"invalid Cursor ownership state: {state_path}")
    owned = state.get("owned_sha256")
    if not isinstance(owned, dict) or not owned:
        raise ValueError(f"missing Cursor ownership hashes: {state_path}")
    if EDITABLE_BINDING not in owned:
        raise ValueError(f"missing Cursor model binding ownership entry: {state_path}")
    _verify_editable_binding(bundle / EDITABLE_BINDING)
    for relative, expected in owned.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError(f"invalid Cursor ownership entry: {state_path}")
        if relative == EDITABLE_BINDING:
            continue
        if relative.startswith("skills/"):
            continue
        path = _project_path_for(relative, rules, bundle)
        if not path.is_file() or _hash(path) != expected:
            raise ValueError(f"Cursor ownership drift: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--source-skills", type=Path)
    args = parser.parse_args()
    try:
        if args.source_skills:
            verify_global_skills(args.skills, args.source_skills)
        if args.state:
            if not args.rules or not args.bundle:
                raise ValueError("--state requires --rules and --bundle")
            verify_project(args.state, args.rules, args.bundle)
        if not args.source_skills and not args.state:
            raise ValueError("supply --source-skills or --state")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
