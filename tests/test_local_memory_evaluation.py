"""Quality gate for the deterministic local-memory evaluation corpus."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_evaluator():
    spec = importlib.util.spec_from_file_location(
        "evaluate_local_memory", ROOT / "tools" / "evaluate_local_memory.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalMemoryEvaluationTests(unittest.TestCase):
    def test_synthetic_retrieval_and_isolation_quality_gate(self):
        report = load_evaluator().evaluate()

        self.assertGreaterEqual(report["recall_at_5"], 0.85)
        self.assertGreaterEqual(report["precision_at_5"], 0.90)
        self.assertEqual(report["cross_namespace_leaks"], 0)


if __name__ == "__main__":
    unittest.main()
