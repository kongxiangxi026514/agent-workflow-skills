"""Executable capability-equivalence checks required before Superpowers removal."""

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "policy-v3" / "capability-equivalence.json"


def _load_tool(name):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapabilityEquivalenceTests(unittest.TestCase):
    """Keep retained workflow capabilities explicit and testable."""

    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads((ROOT / "policy-v3" / "registry.json").read_text(encoding="utf-8"))

    def test_matrix_covers_required_retained_capabilities(self):
        required = {
            "formal-r2-design-approval",
            "task-ledger-checkpoint-handoff",
            "worktree-branch-lifecycle",
            "review-feedback-triage",
            "grill-gate",
            "test-first-development",
            "verification-and-closeout",
        }
        actual = {capability["id"] for capability in self.matrix["capabilities"]}
        self.assertEqual(actual, required)
        self.assertEqual(
            set(self.matrix["explicitly_excluded"]),
            {
                "verbose-repeated-prompts",
                "mandatory-per-turn-announcements",
                "unconditional-full-lifecycle",
            },
        )

    def test_matrix_evidence_exists_in_canonical_policies(self):
        policies = {policy["policy_id"]: policy for policy in self.registry["policies"]}
        for capability in self.matrix["capabilities"]:
            with self.subTest(capability=capability["id"]):
                evidence = capability["v3_evidence"]
                policy = policies[evidence["policy_id"]]
                source = ROOT / policy["source"]
                self.assertEqual(source.as_posix().endswith(evidence["source"]), True)
                text = source.read_text(encoding="utf-8").lower()
                for marker in evidence["required_markers"]:
                    self.assertIn(marker.lower(), text)

    def test_formal_design_and_grilling_golden_cases_route_strictly(self):
        router = _load_tool("policy_router")
        for case in self.matrix["golden_cases"]:
            with self.subTest(case=case["id"]):
                result = router.route_task(case["text"], case["paths"], root=ROOT)
                self.assertEqual(result["risk"], case["expected_risk"])
                self.assertEqual(result["loaded_policy_ids"], case["expected_policies"])

    def test_equivalence_gate_preserves_rendering_and_token_budgets(self):
        audit = _load_tool("audit_context_budget").audit(ROOT)
        limits = self.registry["token_proxy"]
        self.assertTrue(audit["passed"], audit)
        self.assertLessEqual(audit["budget"]["l0_token_proxy"], limits["l0_max"])
        self.assertLessEqual(audit["budget"]["max_fragment_token_proxy"], limits["fragment_max"])


if __name__ == "__main__":
    unittest.main()
