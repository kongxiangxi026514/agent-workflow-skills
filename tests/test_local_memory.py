"""Contract tests for the local-only transactional OpenCode memory store."""

from __future__ import annotations

import concurrent.futures
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_memory():
    path = ROOT / "tools" / "local_memory.py"
    spec = importlib.util.spec_from_file_location("local_memory", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.memory = load_memory()

    def tearDown(self):
        self.temp.cleanup()

    def store(self, scope="global", project_root=None):
        return self.memory.MemoryStore(
            self.root,
            scope=scope,
            project_root=project_root,
        )

    def test_explicit_preference_promotes_without_storing_raw_message(self):
        store = self.store()
        raw = "Please remember: I prefer focused regression tests before implementation."

        result = store.capture(raw, outcome="success")

        self.assertEqual(result["promoted"], 1)
        rows = store.search("focused regression", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertIn("focused regression tests", rows[0]["summary"])
        self.assertNotIn(raw, store.database_path.read_text(encoding="utf-8", errors="ignore"))

    def test_secret_canary_is_never_persisted(self):
        store = self.store()
        sentinel = "LEAK-CANARY-4e7c48c5"

        result = store.capture(f"My token is {sentinel}; remember it.", outcome="success")

        self.assertEqual(result["rejected"], 1)
        for path in (store.database_path, store.database_path.with_name(f"{store.database_path.name}-wal")):
            if path.exists():
                self.assertNotIn(sentinel.encode(), path.read_bytes())

    def test_project_fact_requires_success_and_never_crosses_namespaces(self):
        project_a = self.root / "project-a"
        project_b = self.root / "project-b"
        project_a.mkdir()
        project_b.mkdir()
        text = "Project convention: run focused tests before changing production code."

        pending = self.store("project", project_a)
        self.assertEqual(pending.capture(text, outcome="pending")["promoted"], 0)
        self.assertEqual(pending.search("focused tests", limit=5), [])

        active = self.store("project", project_a)
        self.assertEqual(active.capture(text, outcome="success")["promoted"], 1)
        self.assertEqual(len(active.search("focused tests", limit=5)), 1)
        self.assertEqual(self.store("global").search("focused tests", limit=5), [])
        self.assertEqual(self.store("project", project_b).search("focused tests", limit=5), [])

    def test_implicit_habit_requires_three_independent_sessions(self):
        store = self.store()
        text = "I tend to prefer small, focused changes."

        for session in ("one", "two"):
            self.assertEqual(store.capture(text, session_id=session, outcome="success")["promoted"], 0)
        self.assertEqual(store.capture(text, session_id="three", outcome="success")["promoted"], 1)
        self.assertEqual(len(store.search("focused changes", limit=5)), 1)

    def test_conflicting_preference_is_quarantined(self):
        store = self.store()
        self.assertEqual(
            store.capture("I prefer concise implementation summaries.", outcome="success")["promoted"],
            1,
        )

        result = store.capture(
            "I prefer exhaustive implementation summaries with every detail.",
            outcome="success",
        )

        self.assertEqual(result["quarantined"], 1)
        rows = store.search("implementation summaries", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertIn("concise", rows[0]["summary"])

    def test_rollback_restores_previous_generation(self):
        store = self.store()
        store.capture("I prefer concise implementation summaries.", outcome="success")
        store.capture("I prefer explicit error messages.", outcome="success")
        generation = store.status()["generation"] - 1

        store.rollback(generation)

        rows = store.search("implementation summaries", limit=5)
        self.assertEqual(len(rows), 1)
        self.assertIn("concise", rows[0]["summary"])

    def test_context_never_exceeds_its_hard_budget(self):
        store = self.store()
        for index in range(12):
            store.capture(
                f"I prefer focused regression checks for module {index}.",
                outcome="success",
            )

        context = store.context("focused regression", token_budget=35)

        self.assertLessEqual(self.memory.token_proxy(context), 35)
        self.assertNotIn("module 11", context)

    def test_concurrent_writers_keep_database_consistent(self):
        def capture(index):
            return self.store().capture(
                f"I prefer deterministic validation step {index}.",
                outcome="success",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(capture, range(8)))

        self.assertTrue(all(result["promoted"] == 1 for result in results))
        self.assertEqual(self.store().status()["active"], 8)
        connection = sqlite3.connect(self.store().database_path)
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_telemetry_retains_hashes_not_prompt_text(self):
        store = self.store()
        prompt = "Never store this exact telemetry prompt."

        store.record_telemetry(
            prompt,
            predicted_policy_ids=["P01"],
            selected_agent="build",
            selected_skills=["workflow-lifecycle"],
            result="completed",
        )

        telemetry = store.status()["telemetry"]
        self.assertEqual(telemetry, 1)
        payload = store.database_path.read_bytes()
        self.assertNotIn(prompt.encode(), payload)


if __name__ == "__main__":
    unittest.main()
