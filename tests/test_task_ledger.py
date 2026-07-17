"""Security contracts for user-approved R2 task-ledger artifacts."""

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_ledger_tool():
    path = ROOT / "tools" / "validate_task_ledger.py"
    spec = importlib.util.spec_from_file_location("validate_task_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskLedgerValidationTests(unittest.TestCase):
    """Keep resumable-task records inside the approved repository boundary."""

    def setUp(self):
        self.ledger = _load_ledger_tool()
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_rejects_absolute_traversal_and_outside_ledger_locations(self):
        for location in (
            "../handoff.md",
            "docs/../../handoff.md",
            str(self.repo.parent / "outside.md"),
            r"C:\outside\handoff.md",
        ):
            with self.subTest(location=location):
                with self.assertRaises(self.ledger.LedgerValidationError):
                    self.ledger.resolve_user_approved_ledger_path(self.repo, location)

    def test_rejects_raw_transcripts_secrets_and_sensitive_command_arguments(self):
        base = self._allowed_ledger()
        disallowed = (
            base + "\n## Raw Transcript\nUser: copy every message here\n",
            base + "\nDecision: api_key=not-a-real-secret\n",
            base + "\nCommand: deploy --token not-a-real-secret\n",
        )
        for text in disallowed:
            with self.subTest(text=text.rsplit("\n", 2)[-2]):
                with self.assertRaises(self.ledger.LedgerValidationError):
                    self.ledger.validate_redacted_ledger(text)

    def test_accepts_a_repository_contained_redacted_ledger(self):
        location = "docs/task-ledgers/equivalence.md"
        resolved = self.ledger.resolve_user_approved_ledger_path(self.repo, location)
        self.assertEqual(resolved, (self.repo / "docs/task-ledgers/equivalence.md").resolve())
        self.assertEqual(self.ledger.validate_redacted_ledger(self._allowed_ledger()), None)

    @staticmethod
    def _allowed_ledger():
        return """# Task Ledger
## Objective
Ship the approved R2 gate.
## Decisions
Keep the artifact lightweight.
## Completed Steps
Added focused tests.
## Failures
None.
## Evidence
`python -m unittest tests.test_task_ledger` passed.
## Next Action
Request review.
## Handoff
Verify the cited test output.
## Redaction
No raw transcripts or sensitive command arguments; values are <redacted>.
"""
