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
import tempfile
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from dispatch_resolver import DispatchResolutionError, _load_binding
from validate_jsonc import parse_jsonc


ROLE_FIELDS = {
    "build": {
        "description": "Configured implementation and orchestration agent.",
        "mode": "primary",
    },
    "reason": {
        "description": "Configured deep-reasoning agent for difficult design and diagnosis.",
        "mode": "subagent",
        "permission": {
            "*": "deny",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "lsp": "allow",
            "skill": "allow",
        },
    },
    "review": {
        "description": "Cross-model reviewer and verifier without edit permission.",
        "mode": "subagent",
        "permission": {
            "*": "deny",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "lsp": "allow",
            "skill": "allow",
        },
    },
}
ROLE_NAMES = tuple(ROLE_FIELDS)
AGENT_ROOTS = ("agent", "agents")
YAML_KEY = re.compile(
    r"""^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*|"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*')\s*:(?P<value>.*)$"""
)
MODEL_KEY = re.compile(r"""^(?:model|"model"|'model')$""", re.IGNORECASE)
AUDIT_VERSION = 1
BUNDLE = "agent-workflow-skills"
MANAGED_MARKER = "<!-- Managed by agent-workflow-skills. -->"
UTF8_BOM = b"\xef\xbb\xbf"
SPINE_BEGIN = "<!-- BEGIN agent-workflow-skills spine -->"
SPINE_END = "<!-- END agent-workflow-skills spine -->"


class MigrationError(ValueError):
    """Raised when a migration cannot complete safely."""


@dataclass(frozen=True)
class Change:
    path: Path
    before: bytes | None
    after: bytes | None
    mode: int | None = None


def _identity(path: Path):
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return None
    file_type = stat.S_IFMT(metadata.st_mode)
    return (
        metadata.st_dev,
        metadata.st_ino,
        file_type,
        None if stat.S_ISDIR(metadata.st_mode) else metadata.st_size,
        None if stat.S_ISDIR(metadata.st_mode) else metadata.st_mtime_ns,
        getattr(metadata, "st_file_attributes", 0),
    )


class MutationGuard:
    """Detect cooperative-path swaps before and after each target mutation."""

    def __init__(self, base: Path, changes: list[Change]):
        self.base = base
        self.expected = {}
        for change in changes:
            self._record_chain(change.path)

    def _chain(self, path: Path):
        current = path
        while True:
            yield current
            if current == self.base:
                return
            current = current.parent

    def _record_chain(self, path: Path) -> None:
        for current in self._chain(path):
            self.expected[str(current)] = _identity(current)

    def assert_stable(self, path: Path) -> None:
        _assert_safe_path(self.base, path)
        for current in self._chain(path):
            expected = self.expected.get(str(current))
            actual = _identity(current)
            if expected != actual:
                raise MigrationError(f"path identity changed during migration: {current}")

    def prepare_parent(self, path: Path) -> None:
        self.assert_stable(path)
        _ensure_dir(path.parent)
        self._record_chain(path.parent)

    def verify_written(self, path: Path, content: bytes) -> None:
        self.assert_stable(path.parent)
        _assert_safe_path(self.base, path)
        if _identity(path) is None or path.read_bytes() != content:
            raise MigrationError(f"path changed after write: {path}")
        self._record_chain(path)

    def verify_deleted(self, path: Path) -> None:
        self.assert_stable(path.parent)
        _assert_safe_path(self.base, path)
        if _identity(path) is not None:
            raise MigrationError(f"path changed after deletion: {path}")
        self._record_chain(path)


class MigrationLock:
    """Best-effort cooperative lock; not a hostile same-user security boundary."""

    def __init__(self, base: Path, state_dir: Path):
        self.base = base
        self.state_dir = state_dir
        self.path = _assert_safe_path(base, state_dir / ".opencode-model-migration.lock")
        self.descriptor = None
        self.identity = None
        self.state_preexisting = state_dir.exists()

    def __enter__(self):
        _ensure_dir(self.state_dir)
        _assert_safe_path(self.base, self.path)
        try:
            self.descriptor = os.open(
                self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            os.write(self.descriptor, str(os.getpid()).encode("ascii"))
            os.fsync(self.descriptor)
            self.identity = _identity(self.path)
        except FileExistsError as error:
            raise MigrationError(
                f"OpenCode model migration lock is already held: {self.path}"
            ) from error
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.descriptor is not None:
            os.close(self.descriptor)
        if self.identity is not None and _identity(self.path) == self.identity:
            self.path.unlink(missing_ok=True)
        if not self.state_preexisting:
            _remove_empty_parents(self.state_dir, self.base)


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


def _assert_no_reparse_path(path: Path) -> Path:
    """Validate an external read-only input such as a staged binding."""
    path = _absolute(path)
    current = path
    while True:
        if _has_reparse_point(current):
            raise MigrationError(f"reparse or symlink paths are not supported: {current}")
        if current.parent == current:
            break
        current = current.parent
    return path


def _assert_tree_no_reparse(base: Path, root: Path) -> None:
    """Reject symlink/reparse descendants before recursively reading or writing."""
    root = _assert_safe_path(base, root)
    if not root.exists():
        return
    if not root.is_dir():
        return
    for entry in os.scandir(root):
        path = _assert_safe_path(base, Path(entry.path))
        if _has_reparse_point(path):
            raise MigrationError(f"reparse or symlink paths are not supported: {path}")
        if entry.is_dir(follow_symlinks=False):
            _assert_tree_no_reparse(base, path)


def _file_mode(path: Path) -> int | None:
    if not path.exists():
        return None
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise MigrationError(f"expected regular file: {path}")
    return stat.S_IMODE(metadata.st_mode)


def _restrictive_mode(mode: int | None) -> int:
    """Preserve an existing owner mode or make the replacement stricter."""
    return 0o600 if mode is None else mode & 0o600


def _ensure_dir(path: Path) -> None:
    """Create missing directories privately without widening existing permissions."""
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    if _has_reparse_point(current):
        raise MigrationError(f"reparse or symlink paths are not supported: {current}")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)


def _check_writable_parent(path: Path) -> None:
    """Prove an existing parent accepts private temporary files before mutation."""
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    if _has_reparse_point(parent):
        raise MigrationError(f"reparse or symlink paths are not supported: {parent}")
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".agent-workflow-check-", dir=parent)
        os.close(descriptor)
        Path(temporary).unlink()
    except OSError as error:
        raise MigrationError(f"cannot write migration target near {path}: {error}") from error


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
        data = parse_jsonc(path.read_bytes().decode("utf-8-sig"))
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
    managed_hashes = {}
    for role in ROLE_NAMES:
        existing = role in roles
        current = roles.get(role, {})
        if not isinstance(current, dict):
            raise MigrationError(f"OpenCode agent.{role} must be an object")
        if existing:
            updated = copy.deepcopy(current)
            if role in {"reason", "review"}:
                updated["permission"] = copy.deepcopy(ROLE_FIELDS[role]["permission"])
            updated["model"] = models[role]
        else:
            updated = {**copy.deepcopy(ROLE_FIELDS[role]), "model": models[role]}
        roles[role] = updated
        managed_hashes[role] = _sha256(models[role].encode("utf-8"))
    return result, managed_hashes


def _strip_model_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise MigrationError("Markdown agent has unterminated frontmatter")
    frontmatter = []
    for index, line in enumerate(lines[1:end], 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            frontmatter.append(line)
            continue
        if (
            stripped.startswith(("?", "-", "{", "["))
            or re.search(r"(^|\s)<<\s*:", stripped)
            or re.search(r"(^|\s)[&*][A-Za-z_]", stripped)
        ):
            raise MigrationError(
                "unsupported YAML aliases, merges, sequences, or complex keys in agent frontmatter"
            )
        match = YAML_KEY.match(line.rstrip("\r\n"))
        if match is None:
            if "model" in stripped.lower():
                raise MigrationError(
                    "unsupported YAML key syntax where a model key cannot be proven absent"
                )
            frontmatter.append(line)
            continue
        key = match["key"]
        if key[:1] in {"'", '"'} and "\\" in key:
            raise MigrationError(
                "unsupported escaped YAML key syntax where a model key cannot be proven absent"
            )
        value = match["value"].strip()
        if value.startswith(("[", "{", "]", "}", "|", ">", "&", "*", "!")):
            raise MigrationError(
                "unsupported YAML scalar or mapping syntax in agent frontmatter"
            )
        if value[:1] in {"'", '"'}:
            quote = value[0]
            escaped = False
            closing = None
            for value_index, char in enumerate(value[1:], 1):
                if quote == '"' and char == "\\" and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    closing = value_index
                    break
                escaped = False
            if closing is None or value[closing + 1 :].strip().split("#", 1)[0].strip():
                raise MigrationError(
                    "malformed quoted YAML scalar in agent frontmatter"
                )
        if not MODEL_KEY.fullmatch(key):
            frontmatter.append(line)
            continue
        next_line = lines[index + 1] if index + 1 < end else ""
        if not value and next_line and len(next_line) - len(next_line.lstrip(" ")) > len(match["indent"]):
            raise MigrationError("unsupported multiline YAML model value")
    return "".join([lines[0], *frontmatter, lines[end], *lines[end + 1 :]])


def _owned_manifest(base: Path, state_dir: Path) -> dict[str, str] | None:
    state_path = _assert_safe_path(base, state_dir / "install-state.json")
    if not state_path.exists():
        return None
    try:
        state = parse_jsonc(state_path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise MigrationError(f"invalid legacy install state: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("bundle") != BUNDLE
        or not isinstance(state.get("version"), int)
        or state.get("platform") != "opencode"
        or not isinstance(state.get("profile"), str)
    ):
        return None
    owned = state.get("owned_sha256", {})
    if not isinstance(owned, dict):
        return None
    return {
        key: value
        for key, value in owned.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _walk_agents(base: Path, root_name: str, root_path: Path):
    _assert_tree_no_reparse(base, root_path)
    for root, directories, files in os.walk(root_path, followlinks=False):
        directories.sort()
        files.sort()
        for name in files:
            if Path(name).suffix.lower() == ".md":
                yield _assert_safe_path(base, Path(root) / name)


def _markdown_changes(base: Path, state_dir: Path) -> list[Change]:
    owned = _owned_manifest(base, state_dir) or {}
    active = []
    normalized = {}
    for root_name in AGENT_ROOTS:
        agents = _assert_safe_path(base, base / root_name)
        if not agents.exists():
            continue
        if not agents.is_dir():
            raise MigrationError(f"OpenCode agent path is not a directory: {agents}")
        for path in _walk_agents(base, root_name, agents):
            relative = path.relative_to(agents)
            name = relative.with_suffix("").as_posix().casefold()
            if name in normalized:
                raise MigrationError(
                    "duplicate normalized OpenCode agent name across active roots: "
                    f"{normalized[name]} and {root_name}/{relative.as_posix()}"
                )
            normalized[name] = f"{root_name}/{relative.as_posix()}"
            active.append((root_name, agents, path, relative))
    changes = []
    for root_name, agents, path, relative in active:
        if path.stem not in ROLE_NAMES:
            continue
        if not path.is_file():
            raise MigrationError(f"OpenCode agent is not a regular Markdown file: {path}")
        try:
            before = path.read_bytes()
            has_bom = before.startswith(UTF8_BOM)
            after = _strip_model_frontmatter(
                before.decode("utf-8-sig")
            ).encode("utf-8")
            if has_bom:
                after = UTF8_BOM + after
        except UnicodeError as error:
            raise MigrationError(f"OpenCode Markdown agent is not UTF-8: {path}") from error
        relative_text = relative.as_posix()
        state_key = f"{root_name}/{relative_text}"
        if (
            MANAGED_MARKER not in before.decode("utf-8-sig")
            or owned.get(state_key) != _sha256(before)
        ):
            raise MigrationError(
                f"named role agent is not bundle-owned: {path}. "
                "Rename or migrate the custom role manually before retrying."
            )
        retired = _assert_safe_path(
            base, state_dir / "retired-agents" / root_name / relative
        )
        if retired.exists():
            raise MigrationError(f"retired role-agent destination already exists: {retired}")
        changes.extend(
            (
                Change(retired, None, after),
                Change(path, before, None, _file_mode(path)),
            )
        )
    return changes


def _write_atomic(
    path: Path,
    content: bytes,
    mode: int | None = None,
    guard: MutationGuard | None = None,
) -> None:
    if guard is not None:
        guard.prepare_parent(path)
    else:
        _ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = None
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "wb", closefd=False) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.fchmod(descriptor, _restrictive_mode(mode))
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, path)
        if guard is not None:
            guard.verify_written(path, content)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _restore_change(change: Change, guard: MutationGuard | None = None) -> None:
    if change.before is None:
        if guard is not None:
            guard.assert_stable(change.path)
        change.path.unlink(missing_ok=True)
        if guard is not None:
            guard.verify_deleted(change.path)
    else:
        _write_atomic(change.path, change.before, change.mode, guard)


def _remove_empty_parents(path: Path, base: Path) -> None:
    current = path
    while current != base:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _apply_transaction(
    changes: list[Change],
    *,
    fail_after_write: int | None = None,
    base: Path,
) -> None:
    applied: list[Change] = []
    guard = MutationGuard(base, changes)
    try:
        for change in changes:
            if change.after is None:
                guard.assert_stable(change.path)
                change.path.unlink(missing_ok=True)
                guard.verify_deleted(change.path)
            else:
                _write_atomic(change.path, change.after, change.mode, guard)
            applied.append(change)
            if fail_after_write is not None and len(applied) >= fail_after_write:
                raise OSError("failure injection requested")
    except (OSError, MigrationError):
        for change in reversed(applied):
            _restore_change(change, guard)
        for change in reversed(applied):
            _remove_empty_parents(change.path.parent, base)
        raise


def _audit_payload(
    base: Path,
    selected: Path,
    changes: list[Change],
    managed_hashes: dict,
    backup_root: Path,
    binding: Path,
    config_after: bytes,
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
        "managed_model_sha256": managed_hashes,
        "binding_sha256": _sha256(binding.read_bytes()),
        "config_sha256": _sha256(config_after),
        "files": files,
    }


def _backup_id(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise MigrationError("backup identifier must contain only letters, digits, _ or -")
    return value


def _preflight_migration_targets(
    base: Path, state_dir: Path, audit: Path, backup_root: Path
) -> None:
    """Validate every migration state/backup destination before outer writes."""
    _assert_tree_no_reparse(base, state_dir)
    backups = _assert_safe_path(base, state_dir / "migration-backups")
    _assert_tree_no_reparse(base, backups)
    if backup_root.exists():
        raise MigrationError(f"migration backup target already exists: {backup_root}")
    if audit.exists() and not audit.is_file():
        raise MigrationError(f"migration audit path is not a regular file: {audit}")
    for target in (state_dir, backups, backup_root, audit):
        _assert_safe_path(base, target)
        _check_writable_parent(target)


@dataclass(frozen=True)
class MigrationPlan:
    base: Path
    state_dir: Path
    backup_root: Path
    changes: tuple[Change, ...]


def build_migration_plan(
    base: Path,
    binding: Path,
    audit: Path,
    explicit: str | None,
    backup_id: str | None = None,
) -> MigrationPlan:
    base = _absolute(base)
    state_dir = _assert_safe_path(base, audit.parent)
    audit = _assert_safe_path(base, audit)
    binding = _assert_no_reparse_path(binding)
    selected = select_config(base, explicit)
    _assert_tree_no_reparse(base, selected.parent)
    data = _read_jsonc_object(selected)
    models = _models(binding)
    updated, managed_hashes = _config_after_migration(data, models)
    config_before = selected.read_bytes() if selected.exists() else None
    config_after = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changes = []
    if config_before != config_after:
        changes.append(Change(selected, config_before, config_after, _file_mode(selected)))
    changes.extend(_markdown_changes(base, state_dir))
    backup_root = _assert_safe_path(
        base, state_dir / "migration-backups" / _backup_id(backup_id)
    )
    _preflight_migration_targets(base, state_dir, audit, backup_root)
    audit_change = []
    if changes:
        payload = _audit_payload(
            base,
            selected,
            changes,
            managed_hashes,
            backup_root,
            binding,
            config_after,
        )
        audit_after = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        existing_audit = audit.read_bytes() if audit.exists() else None
        audit_change = [Change(audit, existing_audit, audit_after, _file_mode(audit))]
    backup_changes = [
        Change(
            _assert_safe_path(base, backup_root / change.path.relative_to(base)),
            None,
            change.before,
            change.mode,
        )
        for change in changes
        if change.before is not None
    ]
    return MigrationPlan(
        base=base,
        state_dir=state_dir,
        backup_root=backup_root,
        changes=tuple(
            [*backup_changes, *changes, *audit_change]
        ),
    )


def migrate(
    base: Path,
    binding: Path,
    audit: Path,
    explicit: str | None,
    fail_after_write: int | None = None,
    check: bool = False,
    backup_id: str | None = None,
) -> None:
    if check:
        build_migration_plan(base, binding, audit, explicit, backup_id)
        return
    absolute_base = _absolute(base)
    state_dir = _assert_safe_path(absolute_base, Path(audit).parent)
    with MigrationLock(absolute_base, state_dir):
        plan = build_migration_plan(absolute_base, binding, audit, explicit, backup_id)
        try:
            _apply_transaction(
                list(plan.changes),
                fail_after_write=fail_after_write,
                base=plan.base,
            )
        except (OSError, MigrationError) as error:
            shutil.rmtree(plan.backup_root, ignore_errors=True)
            _remove_empty_parents(plan.backup_root.parent, plan.state_dir)
            raise MigrationError(f"migration rolled back: {error}") from error


def _assert_external_tree_no_reparse(root: Path) -> None:
    root = _assert_no_reparse_path(root)
    if not root.exists():
        raise MigrationError(f"required staged artifact is missing: {root}")
    if root.is_dir():
        for entry in os.scandir(root):
            path = Path(entry.path)
            if _has_reparse_point(path):
                raise MigrationError(f"staged artifact uses a reparse path: {path}")
            if entry.is_dir(follow_symlinks=False):
                _assert_external_tree_no_reparse(path)


def _tree_files(root: Path) -> dict[Path, bytes]:
    _assert_external_tree_no_reparse(root)
    if not root.is_dir():
        raise MigrationError(f"expected directory: {root}")
    result = {}
    for directory, _, files in os.walk(root, followlinks=False):
        for name in sorted(files):
            path = Path(directory) / name
            if _has_reparse_point(path) or not path.is_file():
                raise MigrationError(f"expected regular staged file: {path}")
            result[path.relative_to(root)] = path.read_bytes()
    return result


def _changes_for_tree(base: Path, source: Path, destination: Path) -> list[Change]:
    desired = _tree_files(source)
    destination = _assert_safe_path(base, destination)
    if destination.exists():
        if not destination.is_dir():
            raise MigrationError(f"expected directory: {destination}")
        _assert_tree_no_reparse(base, destination)
        existing = {
            path.relative_to(destination): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        }
    else:
        existing = {}
    changes = []
    for relative in sorted(desired):
        target = _assert_safe_path(base, destination / relative)
        before = existing.get(relative)
        if before != desired[relative]:
            changes.append(Change(target, before, desired[relative], _file_mode(target)))
    for relative in sorted(set(existing) - set(desired), reverse=True):
        target = _assert_safe_path(base, destination / relative)
        changes.append(Change(target, existing[relative], None, _file_mode(target)))
    return changes


def _spine_text(existing: bytes | None, adapter: bytes) -> bytes:
    try:
        content = "" if existing is None else existing.decode("utf-8-sig")
        source = adapter.decode("utf-8")
    except UnicodeError as error:
        raise MigrationError(f"OpenCode spine is not UTF-8: {error}") from error
    begin_count = content.count("<!-- BEGIN agent-workflow-skills spine -->")
    end_count = content.count("<!-- END agent-workflow-skills spine -->")
    if (begin_count, end_count) not in {(0, 0), (1, 1)}:
        raise MigrationError("corrupted agent-workflow-skills spine markers")
    body = re.sub(
        r"\A---\r?\n.*?\r?\n---\r?\n",
        "",
        source,
        count=1,
        flags=re.DOTALL,
    ).strip()
    block = (
        "<!-- BEGIN agent-workflow-skills spine -->\n"
        f"{body}\n"
        "<!-- END agent-workflow-skills spine -->"
    )
    if begin_count:
        start = content.index("<!-- BEGIN agent-workflow-skills spine -->")
        end = content.index("<!-- END agent-workflow-skills spine -->")
        if end < start:
            raise MigrationError("corrupted agent-workflow-skills spine markers")
        return (content[:start] + block + content[end + len("<!-- END agent-workflow-skills spine -->") :]).encode("utf-8")
    return ((content.rstrip() + ("\n\n" if content.strip() else "") + block + "\n").encode("utf-8"))


def _spine_block_digest(content: bytes) -> str | None:
    text = content.decode("utf-8-sig")
    if SPINE_BEGIN not in text and SPINE_END not in text:
        return None
    if text.count(SPINE_BEGIN) != 1 or text.count(SPINE_END) != 1:
        raise MigrationError("corrupted agent-workflow-skills spine markers")
    body = text.split(SPINE_BEGIN, 1)[1].split(SPINE_END, 1)[0].strip("\r\n")
    return _sha256(f"{SPINE_BEGIN}\n{body}\n{SPINE_END}".encode("utf-8"))


def _verify_spine_ownership(base: Path, state_dir: Path, content: bytes | None) -> None:
    if content is None:
        return
    digest = _spine_block_digest(content)
    if digest is None:
        return
    state_path = _assert_safe_path(base, state_dir / "install-state.json")
    if not state_path.exists():
        raise MigrationError(
            "existing managed spine marker has no valid ownership state"
        )
    try:
        state = parse_jsonc(state_path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise MigrationError(f"invalid managed spine state: {error}") from error
    if (
        not isinstance(state, dict)
        or state.get("bundle") != BUNDLE
        or state.get("platform") != "opencode"
        or not isinstance(state.get("spine_block_sha256"), str)
        or state["spine_block_sha256"] != digest
    ):
        raise MigrationError(
            "existing managed spine marker lacks valid hash provenance"
        )


def _bundle_changes(base: Path, stage: Path, state_dir: Path) -> list[Change]:
    stage = _assert_no_reparse_path(stage)
    _assert_external_tree_no_reparse(stage)
    skills_source = stage / "skills"
    _assert_external_tree_no_reparse(skills_source)
    skills_destination = _assert_safe_path(base, base / "skills")
    owned = _owned_manifest(base, state_dir)
    changes = []
    for source in sorted(skills_source.iterdir()):
        if not source.is_dir():
            continue
        destination = _assert_safe_path(base, skills_destination / source.name)
        if destination.exists():
            marker = destination / ".agent-workflow-skills-owned"
            skill = destination / "SKILL.md"
            key = f"skills/{source.name}/SKILL.md"
            if (
                not marker.is_file()
                or not skill.is_file()
                or owned is None
                or owned.get(key) != _sha256(skill.read_bytes())
            ):
                raise MigrationError(
                    f"skill ownership marker or manifest is invalid: {destination}"
                )
        changes.extend(_changes_for_tree(base, source, destination))
    agents = _assert_safe_path(base, base / "AGENTS.md")
    adapter = stage / "workflow-gate.mdc"
    if not adapter.is_file():
        raise MigrationError(f"required staged artifact is missing: {adapter}")
    before = agents.read_bytes() if agents.exists() else None
    _verify_spine_ownership(base, state_dir, before)
    after = _spine_text(before, adapter.read_bytes())
    if before != after:
        changes.append(Change(agents, before, after, _file_mode(agents)))
    for name in (
        "model-routing.jsonc",
        "dispatch_resolver.py",
        "validate_jsonc.py",
        "install-state.json",
    ):
        source = stage / name
        if not source.is_file():
            raise MigrationError(f"required staged artifact is missing: {source}")
        target = _assert_safe_path(base, state_dir / name)
        before = target.read_bytes() if target.exists() else None
        after = source.read_bytes()
        if before != after:
            changes.append(Change(target, before, after, _file_mode(target)))
    for change in changes:
        _check_writable_parent(change.path)
    return changes


def install_transaction(
    base: Path,
    binding: Path,
    audit: Path,
    explicit: str | None,
    stage: Path,
    *,
    check: bool = False,
    fail_after_write: int | None = None,
    backup_id: str | None = None,
) -> None:
    if check:
        plan = build_migration_plan(base, binding, audit, explicit, backup_id)
        _bundle_changes(plan.base, stage, plan.state_dir)
        return
    absolute_base = _absolute(base)
    state_dir = _assert_safe_path(absolute_base, Path(audit).parent)
    with MigrationLock(absolute_base, state_dir):
        plan = build_migration_plan(absolute_base, binding, audit, explicit, backup_id)
        outer = _bundle_changes(plan.base, stage, plan.state_dir)
        try:
            _apply_transaction(
                [*plan.changes, *outer],
                fail_after_write=fail_after_write,
                base=plan.base,
            )
        except (OSError, MigrationError) as error:
            shutil.rmtree(plan.backup_root, ignore_errors=True)
            _remove_empty_parents(plan.backup_root.parent, plan.state_dir)
            raise MigrationError(f"OpenCode install rolled back: {error}") from error


def _failure_injection(value: int | None) -> int | None:
    if value is not None:
        return value
    raw = os.environ.get("AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER")
    if raw is None:
        return None
    try:
        injected = int(raw)
    except ValueError as error:
        raise MigrationError(
            "AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER must be an integer"
        ) from error
    if injected < 1:
        raise MigrationError(
            "AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER must be positive"
        )
    return injected


def _validate_audit(audit: dict) -> tuple[str, dict]:
    if audit.get("bundle") != BUNDLE or audit.get("version") != AUDIT_VERSION:
        raise MigrationError("unrecognized OpenCode model migration audit")
    config = audit.get("config")
    model_hashes = audit.get("managed_model_sha256")
    if not isinstance(config, str) or not isinstance(model_hashes, dict):
        raise MigrationError("invalid OpenCode model migration audit")
    for role in ROLE_FIELDS:
        expected = model_hashes.get(role)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise MigrationError(f"invalid managed role audit for {role}")
    for key in ("binding_sha256", "config_sha256"):
        value = audit.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise MigrationError(f"invalid OpenCode model migration audit {key}")
    return config, model_hashes


def uninstall(base: Path, audit_path: Path, *, check: bool = False) -> None:
    base = _absolute(base)
    audit_path = _assert_safe_path(base, audit_path)
    if not audit_path.exists():
        return
    _assert_tree_no_reparse(base, audit_path.parent)
    try:
        audit = parse_jsonc(audit_path.read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise MigrationError(f"invalid OpenCode model migration audit: {error}") from error
    config_relative, model_hashes = _validate_audit(audit)
    config = _assert_safe_path(base, base / config_relative)
    if config.name not in {"opencode.json", "opencode.jsonc"} or not config.exists():
        raise MigrationError("managed OpenCode config is missing or invalid")
    _assert_tree_no_reparse(base, config.parent)
    data = _read_jsonc_object(config)
    roles = data.get("agent")
    if not isinstance(roles, dict):
        raise MigrationError("managed OpenCode agent configuration is missing")
    for role, expected_hash in model_hashes.items():
        current = roles.get(role)
        if (
            not isinstance(current, dict)
            or not isinstance(current.get("model"), str)
            or _sha256(current["model"].encode("utf-8")) != expected_hash
        ):
            raise MigrationError(
                f"managed OpenCode role model drifted: {role}"
            )
    if check:
        return
    for role in model_hashes:
        current = roles[role]
        del current["model"]
        if not current:
            del roles[role]
    if not roles:
        del data["agent"]
    before = config.read_bytes()
    mode = _file_mode(config)
    after = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _write_atomic(config, after, mode)
        audit_path.unlink()
    except OSError as error:
        _write_atomic(config, before, mode)
        raise MigrationError(f"uninstall rolled back: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--opencode-model-config")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fail-after-write", type=int)
    parser.add_argument("--backup-id")
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    try:
        if args.fail_after_write is not None and args.fail_after_write < 1:
            raise MigrationError("--fail-after-write must be positive")
        if args.uninstall:
            if args.fail_after_write is not None or args.backup_id or args.stage:
                raise MigrationError("--backup-id, --stage and --fail-after-write are only valid for migration")
            uninstall(args.config_dir, args.audit, check=args.check)
        elif args.stage:
            install_transaction(
                args.config_dir,
                args.binding,
                args.audit,
                args.opencode_model_config,
                args.stage,
                check=args.check,
                fail_after_write=_failure_injection(args.fail_after_write),
                backup_id=args.backup_id,
            )
        else:
            migrate(
                args.config_dir,
                args.binding,
                args.audit,
                args.opencode_model_config,
                _failure_injection(args.fail_after_write),
                args.check,
                args.backup_id,
            )
    except (MigrationError, OSError, UnicodeError) as error:
        print(f"OpenCode model migration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
