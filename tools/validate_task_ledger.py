"""Validate the location and redaction boundary of a task-ledger artifact."""

from __future__ import annotations

import argparse
import re
from pathlib import Path, PureWindowsPath


class LedgerValidationError(ValueError):
    """Raised when a resumable-task record would violate its safety contract."""


_HEADINGS = (
    "Objective",
    "Decisions",
    "Completed Steps",
    "Failures",
    "Evidence",
    "Next Action",
    "Handoff",
    "Redaction",
)
_RAW_TRANSCRIPT = re.compile(r"(?im)^#{1,6}\s*(?:raw\s+)?transcripts?\b")
_SECRET_VALUE = re.compile(
    r"(?im)\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret)\b\s*[:=]\s*(?!<redacted>|\[redacted\])\S+"
)
_SENSITIVE_ARGUMENT = re.compile(
    r"(?im)(?:--(?:api[_-]?key|token|password|secret)|authorization:)\s+(?!<redacted>|\[redacted\])\S+"
)


def resolve_user_approved_ledger_path(repo_root: Path | str, approved_location: str) -> Path:
    """Resolve an explicitly approved ledger path only when it stays in the repository."""
    if not isinstance(approved_location, str) or not approved_location.strip():
        raise LedgerValidationError("ledger location must be a non-empty user-approved relative path")
    candidate = Path(approved_location)
    windows_candidate = PureWindowsPath(approved_location)
    if candidate.is_absolute() or candidate.anchor or windows_candidate.is_absolute() or windows_candidate.anchor:
        raise LedgerValidationError("ledger location must not be absolute")
    if any(part == ".." for part in candidate.parts) or any(part == ".." for part in windows_candidate.parts):
        raise LedgerValidationError("ledger location must not traverse outside the repository")
    root = Path(repo_root).resolve()
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise LedgerValidationError("ledger location resolves outside the repository") from error
    return target


def validate_redacted_ledger(text: str) -> None:
    """Reject raw transcripts, secret-like values, and unredacted sensitive arguments."""
    if not isinstance(text, str):
        raise LedgerValidationError("ledger content must be text")
    missing = [heading for heading in _HEADINGS if f"## {heading}" not in text]
    if missing:
        raise LedgerValidationError(f"ledger is missing required sections: {', '.join(missing)}")
    if "<redacted>" not in text.lower() and "[redacted]" not in text.lower():
        raise LedgerValidationError("ledger must declare redacted records")
    if _RAW_TRANSCRIPT.search(text):
        raise LedgerValidationError("ledger must not contain raw transcripts")
    if _SECRET_VALUE.search(text):
        raise LedgerValidationError("ledger must not contain secret-like values")
    if _SENSITIVE_ARGUMENT.search(text):
        raise LedgerValidationError("ledger must not contain sensitive command arguments")


def main() -> int:
    """Validate a single, repository-contained, explicitly approved ledger file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--approved-location", required=True)
    args = parser.parse_args()
    try:
        ledger = resolve_user_approved_ledger_path(args.repo, args.approved_location)
        validate_redacted_ledger(ledger.read_text(encoding="utf-8"))
    except (LedgerValidationError, OSError, UnicodeError) as error:
        print(error)
        return 1
    print(ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
