"""Contract tests for portable rendering of project policy extensions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _canonical_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def _policy(policy_id: str, source: str, artifact: str, selector: str, trigger: str) -> dict:
    return {
        "policy_id": policy_id,
        "name": f"project-{policy_id.lower()}",
        "tier": "L2" if policy_id != "P25" else "L3",
        "description": f"Project contract {policy_id}.",
        "trigger": {"any": [trigger], "none": []},
        "path_selectors": [selector],
        "cursor_globs": ["src/example/**"] if policy_id != "P25" else [],
        "risk": "R2" if policy_id != "P25" else "R0",
        "budget_tokens": 500,
        "source": source,
        "artifact": artifact,
        "on_demand": True,
    }


def _write_extension(project_root: Path, registry_sha256: str) -> None:
    policy_root = project_root / "workflow-policy"
    policy_root.mkdir()
    policies = []
    for index in range(20, 26):
        policy_id = f"P{index}"
        source = f"workflow-policy/{policy_id}.md"
        artifact = (
            f"workflow-policy/generated/index/{policy_id}.md"
            if policy_id == "P25"
            else f"workflow-policy/generated/cursor/{policy_id}.mdc"
        )
        (project_root / source).write_text(f"# {policy_id}\n\nProject source.\n", encoding="utf-8")
        policies.append(_policy(policy_id, source, artifact, rf"^src/{policy_id.lower()}/", policy_id.lower()))
    overlay = {
        "schema_version": "3.0",
        "base_registry": {
            "revision": "a" * 40,
            "registry_sha256": registry_sha256,
            "policy_ids": [f"P0{index}" for index in range(8)],
        },
        "policies": policies,
    }
    (policy_root / "overlay.json").write_text(json.dumps(overlay), encoding="utf-8")


class ProjectExtensionRendererTests(unittest.TestCase):
    def load_tool(self):
        path = ROOT / "tools" / "render_project_extension.py"
        self.assertTrue(path.is_file(), f"missing project extension renderer: {path.relative_to(ROOT)}")
        spec = importlib.util.spec_from_file_location("render_project_extension", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_extension_is_pinned_routed_and_rendered_deterministically(self):
        renderer = self.load_tool()
        registry_sha256 = hashlib.sha256(
            _canonical_text(ROOT / "policy-v3" / "registry.json").encode("utf-8")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            _write_extension(project_root, registry_sha256)

            report = renderer.validate_extension(ROOT, project_root)
            self.assertEqual(report["errors"], [])
            self.assertEqual(
                renderer.select_extension_policy_ids(
                    renderer.load_extension(project_root),
                    "Review a P25 historical migration.",
                    ["docs/history.md"],
                ),
                ["P25"],
            )
            self.assertEqual(
                renderer.select_extension_policy_ids(
                    renderer.load_extension(project_root),
                    "Implement a helper.",
                    ["src/p22/model.py"],
                ),
                ["P22"],
            )
            expected = renderer.expected_extension_outputs(ROOT, project_root)
            self.assertIn(Path("workflow-policy/generated/cursor/project-extension-router.mdc"), expected)
            self.assertIn(Path("workflow-policy/generated/cursor/P20.mdc"), expected)
            self.assertIn(Path("workflow-policy/generated/index/P25.md"), expected)
            self.assertIn(Path("workflow-policy/generated/manifest.json"), expected)
            self.assertEqual(renderer.detect_extension_drift(project_root, expected), sorted(
                path.as_posix() for path in expected
            ))

            renderer.write_extension_outputs(project_root, expected)
            self.assertEqual(renderer.detect_extension_drift(project_root, expected), [])
            rendered = (project_root / "workflow-policy/generated/cursor/P20.mdc").read_text(encoding="utf-8")
            self.assertIn("project_extension_sha256=", rendered)
            self.assertIn("base_registry_sha256=", rendered)
            self.assertIn("globs:", rendered)

    def test_extension_rejects_wrong_portable_registry_fingerprint(self):
        renderer = self.load_tool()
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            _write_extension(project_root, "0" * 64)

            report = renderer.validate_extension(ROOT, project_root)

        self.assertTrue(any("registry_sha256" in error for error in report["errors"]))

    def test_canonical_renderer_accepts_project_extension_root(self):
        registry_sha256 = hashlib.sha256(
            _canonical_text(ROOT / "policy-v3" / "registry.json").encode("utf-8")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            project_root = Path(temp)
            _write_extension(project_root, registry_sha256)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "render_policy.py"),
                    "--project-root",
                    str(project_root),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"artifacts": 8', result.stdout)


if __name__ == "__main__":
    unittest.main()
