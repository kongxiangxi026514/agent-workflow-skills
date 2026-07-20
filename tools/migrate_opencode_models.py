"""Atomically migrate OpenCode role models into one selected JSON/JSONC config."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from dispatch_resolver import DispatchResolutionError, _load_binding
from validate_jsonc import normalize_jsonc


ROLE_FIELDS = {
    "build": {
        "description": "Configured implementation and orchestration agent.",
        "mode": "primary",
    },
    "reason": {
        "description": "Configured deep-reasoning agent for difficult design and diagnosis.",
        "mode": "subagent",
    },
    "review": {
        "description": "Cross-model reviewer and verifier without edit permission.",
        "mode": "subagent",
        "permission": {"edit": "deny"},
    },
}
ROLE_NAMES = tuple(ROLE_FIELDS)
MODEL_LINE = re.compile(r"^model\s*:", re.IGNORECASE)
AUDIT_VERSION = 1
BUNDLE = "agent-workflow-skills"


class MigrationError(ValueError):
    """Raised when a migration cannot complete safely."""


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes | None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _has_reparse_point(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _assert_safe_path(base: Path, path: Path) -> Path:
    base = _absolute(base)
    path = _absolute(path)
    try:
        path.relative_to(base)
    except ValueError as error:
        raise MigrationError(f"path escapes OpenCode config directory: {path}") from error
    current = path
    while True:
        if _has_reparse_point(current):
            raise MigrationError(f"reparse or symlink paths are not supported: {current}")
        if current == base:
            break
        current = current.parent
    return path


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def select_config(base: Path, explicit: str | None) -> Path:
    """Choose a single safe target without silently resolving config ambiguity."""
    base = _absolute(base)
    _assert_safe_path(base, base)
    json_path = _assert_safe_path(base, base / "opencode.json")
    jsonc_path = _assert_safe_path(base, base / "opencode.jsonc")
    existing = [path for path in (json_path, jsonc_path) if path.exists()]
    if len(existing) == 2:
        raise MigrationError(
            "both opencode.json and opencode.jsonc exist; select one manually after removing ambiguity"
        )
    if explicit:
        selected = Path(explicit)
        if not selected.is_absolute():
            selected = base / selected
        selected = _assert_safe_path(base, selected)
        if selected.name not in {"opencode.json", "opencode.jsonc"}:
            raise MigrationError(
                "--opencode-model-config must name opencode.json or opencode.jsonc"
            )
        allowed = json_path if selected.name == "opencode.json" else jsonc_path
        if not _same_path(selected, allowed):
            raise MigrationError(
                "--opencode-model-config must be inside the OpenCode config directory"
            )
        return allowed
    if existing:
        return existing[0]
    return jsonc_path


def _read_jsonc_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(normalize_jsonc(path.read_bytes().decode("utf-8-sig")))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise MigrationError(f"invalid OpenCode JSON/JSONC config: {error}") from error
    if not isinstance(data, dict):
        raise MigrationError("OpenCode config root must be an object")
    return data


def _models(binding: Path) -> dict[str, str]:
    try:
        return _load_binding("opencode", binding)["models"]
    except DispatchResolutionError as error:
        raise MigrationError(f"invalid OpenCode model binding: {error}") from error


def _config_after_migration(data: dict, models: dict[str, str]) -> tuple[dict, dict]:
    result = copy.deepcopy(data)
    roles = result.setdefault("agent", {})
    if not isinstance(roles, dict):
        raise MigrationError("OpenCode agent configuration must be an object")
    managed = {}
    for role in ROLE_NAMES:
        current = roles.get(role, {})
        if not isinstance(current, dict):
            raise MigrationError(f"OpenCode agent.{role} must be an object")
        expected = {**ROLE_FIELDS[role], "model": models[role]}
        updated = dict(current)
        updated.update(copy.deepcopy(expected))
        roles[role] = updated
        managed[role] = expected
    return result, managed


def _strip_model_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise MigrationError("Markdown agent has unterminated frontmatter")
    frontmatter = [
        line for line in lines[1:end] if not MODEL_LINE.match(line.lstrip())
    ]
    return "".join([lines[0], *frontmatter, lines[end], *lines[end + 1 :]])


def _markdown_changes(base: Path, state_dir: Path) -> list[Change]:
    agents = _assert_safe_path(base, base / "agents")
    if not agents.exists():
        return []
    if not agents.is_dir():
        raise MigrationError(f"OpenCode agents path is not a directory: {agents}")
    changes = []
    for path in sorted(agents.iterdir()):
        if path.suffix.lower() != ".md":
            continue
        path = _assert_safe_path(base, path)
        if not path.is_file():
            raise MigrationError(f"OpenCode agent is not a regular Markdown file: {path}")
        try:
            before = path.read_bytes()
            after = _strip_model_frontmatter(before.decode("utf-8")).encode("utf-8")
        except UnicodeError as error:
            raise MigrationError(f"OpenCode Markdown agent is not UTF-8: {path}") from error
        if path.stem not in ROLE_NAMES:
            if after != before:
                changes.append(Change(path, before, after))
            continue
        retired = _assert_safe_path(base, state_dir / "retired-agents" / path.name)
        if retired.exists():
            raise MigrationError(f"retired role-agent destination already exists: {retired}")
        changes.extend((Change(retired, None, after), Change(path, before, None)))
    return changes


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _apply_changes(
    changes: list[Change],
    *,
    fail_after_write: int | None = None,
) -> None:
    applied = 0
    try:
        for change in changes:
            if change.after is None:
                change.path.unlink(missing_ok=True)
            else:
                _write_atomic(change.path, change.after)
            applied += 1
            if fail_after_write is not None and applied >= fail_after_write:
                raise OSError("failure injection requested")
    except OSError:
        for change in reversed(changes[:applied]):
            if change.before is None:
                change.path.unlink(missing_ok=True)
            else:
                _write_atomic(change.path, change.before)
        raise


def _audit_payload(
    base: Path,
    selected: Path,
    changes: list[Change],
    managed: dict,
    backup_root: Path,
) -> dict:
    files = []
    for change in changes:
        relative = change.path.relative_to(base).as_posix()
        backup = None
        if change.before is not None:
            backup = (backup_root / relative).relative_to(
                backup_root.parents[1]
            ).as_posix()
        files.append(
            {
                "path": relative,
                "backup": backup,
                "before_sha256": None if change.before is None else _sha256(change.before),
                "after_sha256": None if change.after is None else _sha256(change.after),
            }
        )
    return {
        "bundle": BUNDLE,
        "version": AUDIT_VERSION,
        "config": selected.relative_to(base).as_posix(),
        "managed_roles": managed,
        "files": files,
    }


def migrate(
    base: Path,
    binding: Path,
    audit: Path,
    explicit: str | None,
    fail_after_write: int | None = None,
) -> None:
    base = _absolute(base)
    state_dir = _assert_safe_path(base, audit.parent)
    audit = _assert_safe_path(base, audit)
    selected = select_config(base, explicit)
    data = _read_jsonc_object(selected)
    models = _models(binding)
    updated, managed = _config_after_migration(data, models)
    config_before = selected.read_bytes() if selected.exists() else None
    config_after = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changes = [Change(selected, config_before, config_after)]
    changes.extend(_markdown_changes(base, state_dir))
    backup_root = state_dir / "migration-backups" / uuid.uuid4().hex
    payload = _audit_payload(base, selected, changes, managed, backup_root)
    audit_after = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    existing_audit = audit.read_bytes() if audit.exists() else None
    backup_changes = [
        Change(backup_root / change.path.relative_to(base), None, change.before)
        for change in changes
        if change.before is not None
    ]
    try:
        _apply_changes(backup_changes)
        _apply_changes(changes, fail_after_write=fail_after_write)
        _write_atomic(audit, audit_after)
    except OSError as error:
        for change in reversed(changes):
            if change.before is None:
                change.path.unlink(missing_ok=True)
            else:
                _write_atomic(change.path, change.before)
        if existing_audit is None:
            audit.unlink(missing_ok=True)
        else:
            _write_atomic(audit, existing_audit)
        shutil.rmtree(backup_root, ignore_errors=True)
        raise MigrationError(f"migration rolled back: {error}") from error


def _validate_audit(audit: dict) -> tuple[str, dict]:
    if audit.get("bundle") != BUNDLE or audit.get("version") != AUDIT_VERSION:
        raise MigrationError("unrecognized OpenCode model migration audit")
    config = audit.get("config")
    managed = audit.get("managed_roles")
    if not isinstance(config, str) or not isinstance(managed, dict):
        raise MigrationError("invalid OpenCode model migration audit")
    for role, fixed in ROLE_FIELDS.items():
        expected = managed.get(role)
        if not isinstance(expected, dict) or not isinstance(expected.get("model"), str):
            raise MigrationError(f"invalid managed role audit for {role}")
        for key, value in fixed.items():
            if expected.get(key) != value:
                raise MigrationError(f"invalid managed role audit for {role}")
    return config, managed


def uninstall(base: Path, audit_path: Path) -> None:
    base = _absolute(base)
    audit_path = _assert_safe_path(base, audit_path)
    if not audit_path.exists():
        return
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MigrationError(f"invalid OpenCode model migration audit: {error}") from error
    config_relative, managed = _validate_audit(audit)
    config = _assert_safe_path(base, base / config_relative)
    if config.name not in {"opencode.json", "opencode.jsonc"} or not config.exists():
        raise MigrationError("managed OpenCode config is missing or invalid")
    data = _read_jsonc_object(config)
    roles = data.get("agent")
    if not isinstance(roles, dict):
        raise MigrationError("managed OpenCode agent configuration is missing")
    for role, expected in managed.items():
        current = roles.get(role)
        if not isinstance(current, dict):
            continue
        for key, value in expected.items():
            if current.get(key) == value:
                del current[key]
        if not current:
            del roles[role]
    if not roles:
        del data["agent"]
    before = config.read_bytes()
    after = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _write_atomic(config, after)
        audit_path.unlink()
    except OSError as error:
        _write_atomic(config, before)
        raise MigrationError(f"uninstall rolled back: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--opencode-model-config")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--fail-after-write", type=int)
    args = parser.parse_args()
    try:
        if args.fail_after_write is not None and args.fail_after_write < 1:
            raise MigrationError("--fail-after-write must be positive")
        if args.uninstall:
            if args.fail_after_write is not None:
                raise MigrationError("--fail-after-write is only valid for migration")
            uninstall(args.config_dir, args.audit)
        else:
            migrate(
                args.config_dir,
                args.binding,
                args.audit,
                args.opencode_model_config,
                args.fail_after_write,
            )
    except (MigrationError, OSError, UnicodeError) as error:
        print(f"OpenCode model migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
