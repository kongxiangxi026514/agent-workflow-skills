"""Contracts for platform-local model resolution and dispatch evidence."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_resolver():
    path = ROOT / "tools" / "dispatch_resolver.py"
    spec = importlib.util.spec_from_file_location("dispatch_resolver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DispatchResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cursor = self.root / "cursor.jsonc"
        self.opencode = self.root / "opencode.jsonc"
        self.cursor.write_text(
            json.dumps(
                {
                    "build": "gpt-5.6-terra-xhigh",
                    "reason": "gpt-5.6-sol-xhigh",
                    "review": "glm-5.2-high",
                    "families": {
                        "build": "gpt-5.6",
                        "reason": "gpt-5.6",
                        "review": "glm-5.2",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.opencode.write_text(
            json.dumps(
                {
                    "build": "huawei/glm5.2",
                    "reason": "huawei/glm5.2",
                    "review": "huawei/kimik2.7",
                    "families": {
                        "build": "glm5.2",
                        "reason": "glm5.2",
                        "review": "kimik2.7",
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_platform_bindings_are_isolated_and_hot_swappable(self):
        resolver = load_resolver()
        policy = ROOT / "policy-v3" / "fragments" / "parallel-dispatch.md"
        policy_before = policy.read_bytes()
        cursor_request = resolver.resolve_dispatch("cursor", "build", self.cursor)
        opencode_request = resolver.resolve_dispatch("opencode", "build", self.opencode)
        self.assertEqual(cursor_request["requested_model"], "gpt-5.6-terra-xhigh")
        self.assertEqual(opencode_request["requested_model"], "huawei/glm5.2")
        data = json.loads(self.cursor.read_text(encoding="utf-8"))
        data["build"] = "composer-2.5-fast"
        self.cursor.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(
            resolver.resolve_dispatch("cursor", "build", self.cursor)["requested_model"],
            "composer-2.5-fast",
        )
        self.assertEqual(
            resolver.resolve_dispatch("opencode", "build", self.opencode)["requested_model"],
            "huawei/glm5.2",
        )
        self.assertEqual(policy.read_bytes(), policy_before)

    def test_registry_validation_fails_loud_without_fallback(self):
        resolver = load_resolver()
        with self.assertRaisesRegex(resolver.DispatchResolutionError, "unavailable"):
            resolver.resolve_dispatch(
                "cursor",
                "review",
                self.cursor,
                available_models={"gpt-5.6-terra-xhigh", "gpt-5.6-sol-xhigh"},
                registry_exposed=True,
            )
        with self.assertRaisesRegex(resolver.DispatchResolutionError, "registry"):
            resolver.resolve_dispatch(
                "cursor", "review", self.cursor, registry_exposed=True
            )

    def test_native_dispatch_uses_exact_model_and_read_only_review(self):
        resolver = load_resolver()
        cursor = resolver.resolve_dispatch("cursor", "review", self.cursor)
        self.assertEqual(
            cursor["native_dispatch"],
            {"subagent_type": "explore", "model": "glm-5.2-high"},
        )
        self.assertTrue(cursor["read_only"])
        opencode = resolver.resolve_dispatch("opencode", "review", self.opencode)
        self.assertEqual(opencode["native_dispatch"], {"agent": "review"})
        self.assertEqual(opencode["native_model_source"], "agent-json-config")

    def test_receipts_require_actual_model_evidence_for_cross_model_claims(self):
        resolver = load_resolver()
        request = resolver.resolve_dispatch("cursor", "review", self.cursor)
        unobserved = resolver.make_receipt(request)
        self.assertIsNone(unobserved["actual_model"])
        self.assertEqual(unobserved["cross_model"], "unverified")
        self.assertEqual(unobserved["review_kind"], "independent-review-unverified")
        observed = resolver.make_receipt(request, actual_model="glm-5.2-high")
        self.assertEqual(observed["actual_model"], "glm-5.2-high")
        self.assertIs(observed["cross_model"], True)
        self.assertEqual(observed["review_kind"], "cross-model-review")
        with self.assertRaisesRegex(resolver.DispatchResolutionError, "fallback"):
            resolver.make_receipt(request, actual_model="composer-2.5-fast")

    def test_same_family_review_is_labeled_independent_context(self):
        resolver = load_resolver()
        data = json.loads(self.cursor.read_text(encoding="utf-8"))
        data["review"] = "composer-2.5-fast"
        data["families"]["review"] = "gpt-5.6"
        self.cursor.write_text(json.dumps(data), encoding="utf-8")
        request = resolver.resolve_dispatch("cursor", "review", self.cursor)
        receipt = resolver.make_receipt(request, actual_model="composer-2.5-fast")
        self.assertIs(receipt["cross_model"], False)
        self.assertEqual(receipt["review_kind"], "independent-context-review")

    def test_portable_dispatch_policy_requires_resolution_and_honest_receipts(self):
        fragment = (
            ROOT / "policy-v3" / "fragments" / "parallel-dispatch.md"
        ).read_text(encoding="utf-8")
        router = (ROOT / "policy-v3" / "fragments" / "l0-router.md").read_text(
            encoding="utf-8"
        )
        cursor_rule = (ROOT / "cursor" / "model-routing.mdc").read_text(
            encoding="utf-8"
        )
        for token in (
            "dispatch_resolver.py",
            "requested_model",
            "actual_model",
            "cross_model",
            "independent-context",
        ):
            self.assertIn(token, fragment)
            self.assertIn(token, cursor_rule)
        for token in ("dispatch_resolver.py", "exact native", "unverified"):
            self.assertIn(token, router)
        self.assertNotIn("__BUILD_MODEL__", cursor_rule)
        self.assertNotIn("__REASON_MODEL__", cursor_rule)
        self.assertNotIn("__REVIEW_MODEL__", cursor_rule)


if __name__ == "__main__":
    unittest.main()
