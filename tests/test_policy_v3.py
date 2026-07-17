"""Contract tests for the side-by-side token-efficient workflow v3."""

import copy
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_ROOT = ROOT / "policy-v3"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2}


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PolicyV3TestCase(unittest.TestCase):
    def load_tool(self, name):
        path = ROOT / "tools" / f"{name}.py"
        self.assertTrue(path.is_file(), f"missing v3 tool: {path.relative_to(ROOT)}")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class RegistryAndCorpusTests(PolicyV3TestCase):
    def test_router_corpora_cover_required_risks_and_policies(self):
        gold = _json(ROOT / "tests/router_gold_cases.json")
        negative = _json(ROOT / "tests/router_negative_cases.json")
        self.assertGreaterEqual(len(gold), 15)
        self.assertGreaterEqual(len(negative), 10)
        self.assertEqual({case["expected_risk"] for case in gold}, set(RISK_ORDER))
        expected = {item for case in gold for item in case["expected_policies"]}
        self.assertEqual(expected, {f"P0{i}" for i in range(1, 8)})
        ids = [case["id"] for case in gold + negative]
        self.assertEqual(len(ids), len(set(ids)))

    def test_registry_is_single_source_with_live_unique_fragments(self):
        path = POLICY_ROOT / "registry.json"
        self.assertTrue(path.is_file(), "canonical policy-v3/registry.json is missing")
        registry = _json(path)
        policies = registry["policies"]
        self.assertEqual({p["policy_id"] for p in policies}, {f"P0{i}" for i in range(8)})
        self.assertEqual(len({p["source"] for p in policies}), len(policies))
        required = {
            "policy_id", "name", "tier", "description", "trigger", "path_selectors",
            "risk", "budget_tokens", "source", "artifact", "on_demand",
        }
        for policy in policies:
            with self.subTest(policy=policy["policy_id"]):
                self.assertTrue(required <= policy.keys())
                self.assertTrue((ROOT / policy["source"]).is_file())
                self.assertLessEqual(policy["budget_tokens"], 3000)
        self.assertEqual(next(p for p in policies if p["policy_id"] == "P00")["tier"], "L0")
        self.assertTrue(all(p["on_demand"] for p in policies if p["tier"] == "L1"))

    def test_agent_facing_fragments_are_english_and_have_no_model_ids(self):
        registry_path = POLICY_ROOT / "registry.json"
        self.assertTrue(registry_path.is_file(), "canonical policy-v3/registry.json is missing")
        registry = _json(registry_path)
        text = "\n".join((ROOT / p["source"]).read_text(encoding="utf-8") for p in registry["policies"])
        self.assertIsNone(re.search(r"[\u4e00-\u9fff]", text))
        for forbidden in ("gpt-5", "claude-", "glm-", "gemini-", "qwen-", "huawei/"):
            self.assertNotIn(forbidden, text.lower())


class RouterAndCapsuleTests(PolicyV3TestCase):
    def test_gold_cases_route_exactly_and_deterministically(self):
        router = self.load_tool("policy_router")
        for case in _json(ROOT / "tests/router_gold_cases.json"):
            with self.subTest(case=case["id"]):
                first = router.route_task(case["text"], case["paths"], root=ROOT)
                second = router.route_task(case["text"], case["paths"], root=ROOT)
                self.assertEqual(first, second)
                self.assertEqual(first["risk"], case["expected_risk"])
                self.assertEqual(first["loaded_policy_ids"], case["expected_policies"])

    def test_negative_cases_do_not_overroute(self):
        router = self.load_tool("policy_router")
        for case in _json(ROOT / "tests/router_negative_cases.json"):
            with self.subTest(case=case["id"]):
                result = router.route_task(case["text"], case["paths"], root=ROOT)
                self.assertLessEqual(RISK_ORDER[result["risk"]], RISK_ORDER[case["max_risk"]])
                self.assertFalse(set(result["loaded_policy_ids"]) & set(case["forbidden_policies"]))

    def test_task_capsule_enforces_required_sections_and_budget(self):
        router = self.load_tool("policy_router")
        capsule = router.build_task_capsule(
            goal="Implement deterministic policy routing with focused tests.",
            non_goals=["Do not install adapters or edit user configuration."],
            risk="R1",
            allowed_scope=["policy-v3/", "tools/", "tests/"],
            forbidden_scope=["real user homes", "installer rollout"],
            acceptance=["Gold and negative cases pass.", "Generated files match canonical sources."],
            loaded_policy_ids=["P01", "P05", "P07"],
            artifact_pointers=["policy-v3/registry.json", "tests/router_gold_cases.json"],
            root=ROOT,
        )
        proxy = router.token_proxy(capsule)
        self.assertGreaterEqual(proxy, 300)
        self.assertLessEqual(proxy, 800)
        for heading in (
            "Goal", "Non-goals", "Risk", "Allowed scope", "Forbidden scope",
            "Acceptance", "Loaded policies", "Artifact pointers",
        ):
            self.assertIn(f"## {heading}", capsule)

    def test_task_capsule_preserves_literal_placeholder_like_user_values(self):
        router = self.load_tool("policy_router")
        literal_goal = "{{RISK}} must remain literal user text."
        capsule = router.build_task_capsule(
            goal=literal_goal,
            non_goals=[],
            risk="R1",
            allowed_scope=["tools/"],
            forbidden_scope=["installer rollout"],
            acceptance=["Focused tests pass."],
            loaded_policy_ids=["P07"],
            artifact_pointers=["policy-v3/fragments/task-capsule.md"],
            root=ROOT,
        )
        self.assertIn(f"## Goal\n\n{literal_goal}", capsule)


class RendererAndAuditTests(PolicyV3TestCase):
    def test_generated_outputs_have_provenance_and_no_drift(self):
        renderer = self.load_tool("render_policy")
        expected = renderer.expected_outputs(ROOT)
        self.assertEqual(renderer.detect_drift(ROOT, expected), [])
        for relative, content in expected.items():
            with self.subTest(path=str(relative)):
                self.assertIn("source_sha256=", content)
                self.assertIn("registry_sha256=", content)
                self.assertIn("policy_id=", content)
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            for relative, content in expected.items():
                target = sandbox / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content.encode("utf-8"))
            first = next(iter(expected))
            (sandbox / first).write_text("stale\n", encoding="utf-8")
            self.assertEqual(renderer.detect_drift(sandbox, expected), [first.as_posix()])

    def test_renderer_rejects_absolute_and_escaping_registry_paths(self):
        renderer = self.load_tool("render_policy")
        cases = (
            ("source", "../outside-source.md"),
            ("source", "policy-v3/fragments/nested/../../../escaped-source.md"),
            ("source", "{absolute_source}"),
            ("artifact", "../outside-artifact.md"),
            ("artifact", "policy-v3/generated/nested/../../../escaped-artifact.md"),
            ("artifact", "{absolute_artifact}"),
        )
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp) / "sandbox"
            shutil.copytree(POLICY_ROOT, sandbox / "policy-v3")
            original_registry = _json(sandbox / "policy-v3/registry.json")
            outside_source = sandbox.parent / "outside-source.md"
            escaped_source = sandbox / "escaped-source.md"
            for source in (outside_source, escaped_source):
                source.write_text("outside policy root\n", encoding="utf-8")
            for field, reference in cases:
                with self.subTest(field=field, reference=reference):
                    registry = copy.deepcopy(original_registry)
                    registry["policies"][0][field] = reference.format(
                        absolute_source=outside_source,
                        absolute_artifact=sandbox.parent / "outside-artifact.md",
                    )
                    (sandbox / "policy-v3/registry.json").write_text(
                        json.dumps(registry), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(ValueError, "outside|absolute"):
                        renderer.expected_outputs(sandbox)

    def test_renderer_does_not_write_outside_generated_root(self):
        renderer = self.load_tool("render_policy")
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp) / "sandbox"
            sandbox.mkdir()
            outside = sandbox.parent / "outside-created.md"
            with self.assertRaisesRegex(ValueError, "outside|absolute"):
                renderer.write_outputs(sandbox, {Path("../outside-created.md"): "danger\n"})
            self.assertFalse(outside.exists())

    def test_budget_duplicate_and_stale_reference_guards_detect_mutations(self):
        audit = self.load_tool("audit_context_budget")
        registry = _json(POLICY_ROOT / "registry.json")
        mutated = copy.deepcopy(registry)
        mutated["policies"][0]["source"] = "policy-v3/fragments/missing.md"
        self.assertTrue(any("stale source" in error for error in audit.validate_registry(ROOT, mutated)))
        repeated = "A deliberately repeated policy paragraph " * 5
        duplicates = audit.find_duplicate_paragraphs({"a.md": repeated, "b.md": repeated})
        self.assertEqual(len(duplicates), 1)
        self.assertGreater(audit.token_proxy("x" * 6001), 1500)

    def test_audit_fails_when_policy_recall_or_precision_drops(self):
        audit = self.load_tool("audit_context_budget")
        baseline = audit._routing_metrics(ROOT)
        for metric in ("policy_recall", "policy_precision"):
            with self.subTest(metric=metric):
                degraded = copy.deepcopy(baseline)
                degraded[metric] = 0.97
                with mock.patch.object(audit, "_routing_metrics", return_value=degraded):
                    self.assertFalse(audit.audit(ROOT)["passed"])

    def test_audit_meets_budget_recall_and_precision_gates(self):
        audit = self.load_tool("audit_context_budget")
        report = audit.audit(ROOT)
        self.assertTrue(report["passed"], report)
        self.assertLessEqual(report["budget"]["l0_token_proxy"], 1500)
        self.assertLessEqual(report["budget"]["max_fragment_token_proxy"], 3000)
        self.assertGreaterEqual(report["routing"]["policy_recall"], 0.98)
        self.assertGreaterEqual(report["routing"]["policy_precision"], 0.98)
        self.assertGreaterEqual(report["routing"]["risk_memory_recall"], 0.98)
        self.assertGreaterEqual(report["routing"]["research_review_recall"], 0.95)
        self.assertLess(report["routing"]["heavy_false_trigger_rate"], 0.10)
        self.assertEqual(report["integrity"]["duplicate_paragraphs"], 0)
        self.assertEqual(report["integrity"]["stale_references"], 0)
        self.assertEqual(report["integrity"]["generated_drift"], 0)


if __name__ == "__main__":
    unittest.main()
