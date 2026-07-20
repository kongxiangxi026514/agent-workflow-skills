"""Adversarial contracts for the atomic OpenCode JSON/JSONC role migration."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "migrate_opencode_models.py"


def parse_jsonc(path: Path) -> dict:
    sys.path.insert(0, str(ROOT / "tools"))
    from validate_jsonc import normalize_jsonc

    return json.loads(normalize_jsonc(path.read_text(encoding="utf-8")))


class OpenCodeModelMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / "配置"
        self.binding = self.base / "agent-workflow-skills" / "model-routing.jsonc"
        self.audit = self.base / "agent-workflow-skills" / "opencode-model-migration.json"
        self.binding.parent.mkdir(parents=True)
        self.binding.write_text(
            json.dumps(
                {
                    "build": "sample/build-v1",
                    "reason": None,
                    "review": "sample/review-v1",
                    "families": {"build": "sample", "reason": None, "review": "review"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(HELPER),
                "--config-dir",
                str(self.base),
                "--binding",
                str(self.binding),
                "--audit",
                str(self.audit),
                *args,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

    def mark_legacy_role_owned(self, role: Path):
        content = role.read_bytes()
        if b"Managed by agent-workflow-skills." not in content:
            role.write_bytes(
                content.rstrip() + b"\n<!-- Managed by agent-workflow-skills. -->\n"
            )
        state = self.binding.parent / "install-state.json"
        relative = role.relative_to(self.base / "agents").as_posix()
        state.write_text(
            json.dumps(
                {
                    "bundle": "agent-workflow-skills",
                    "owned_sha256": {
                        f"agents/{relative}": hashlib.sha256(role.read_bytes()).hexdigest()
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_jsonc_migration_preserves_semantics_and_audits_raw_backup(self):
        config = self.base / "opencode.jsonc"
        before = (
            b'// \xe7\x94\xa8\xe6\x88\xb7\xe6\xb3\xa8\xe9\x87\x8a\n'
            b'{"user":{"\xe8\xb7\xaf\xe5\xbe\x84":"\xe4\xbf\x9d\xe7\x95\x99",},'
            b'"agent":{"custom":{"description":"keep",},},}\n'
        )
        config.write_bytes(before)
        agents = self.base / "agents"
        agents.mkdir()
        (agents / "build.md").write_text(
            "---\ndescription: legacy\nmodel: sample/legacy\n---\n", encoding="utf-8"
        )
        self.mark_legacy_role_owned(agents / "build.md")
        helper = agents / "github-helper.md"
        helper.write_text(
            "---\ndescription: helper\nmodel: sample/helper\n---\nbody\n",
            encoding="utf-8",
        )

        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

        migrated = parse_jsonc(config)
        self.assertEqual(migrated["user"], {"路径": "保留"})
        self.assertEqual(migrated["agent"]["custom"], {"description": "keep"})
        self.assertEqual(migrated["agent"]["build"]["model"], "sample/build-v1")
        self.assertEqual(migrated["agent"]["reason"]["model"], "sample/build-v1")
        self.assertEqual(migrated["agent"]["review"]["model"], "sample/review-v1")
        self.assertEqual(migrated["agent"]["review"]["permission"], {"edit": "deny"})
        self.assertNotIn("model:", helper.read_text(encoding="utf-8"))
        self.assertFalse((agents / "build.md").exists())
        retired = self.base / "agent-workflow-skills" / "retired-agents" / "build.md"
        self.assertIn("description: legacy", retired.read_text(encoding="utf-8"))
        self.assertNotIn("model:", retired.read_text(encoding="utf-8"))

        audit = json.loads(self.audit.read_text(encoding="utf-8"))
        config_audit = next(item for item in audit["files"] if item["path"] == "opencode.jsonc")
        backup = self.audit.parent / config_audit["backup"]
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(config_audit["before_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(config_audit["after_sha256"], hashlib.sha256(config.read_bytes()).hexdigest())

    def test_selects_explicit_or_sole_config_and_rejects_ambiguous_pair(self):
        json_path = self.base / "opencode.json"
        jsonc_path = self.base / "opencode.jsonc"
        json_path.write_text('{"user":"json"}\n', encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(parse_jsonc(json_path)["user"], "json")

        self.temp.cleanup()
        self.setUp()
        json_path = self.base / "opencode.json"
        jsonc_path = self.base / "opencode.jsonc"
        json_path.write_text("{}\n", encoding="utf-8")
        jsonc_path.write_text("{}\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in (json_path, jsonc_path)}
        result = self.invoke("--opencode-model-config", str(json_path))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"both", result.stderr.lower())
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_creates_jsonc_and_failure_injection_rolls_everything_back(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertTrue((self.base / "opencode.jsonc").is_file())

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        agent = self.base / "agents" / "github-helper.md"
        agent.parent.mkdir()
        agent.write_text("---\nmodel: sample/helper\n---\n", encoding="utf-8")
        legacy = agent.parent / "build.md"
        legacy.write_text("---\nmodel: sample/legacy\n---\n", encoding="utf-8")
        self.mark_legacy_role_owned(legacy)
        result = self.invoke("--fail-after-write", "6")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertIn("model:", agent.read_text(encoding="utf-8"))
        self.assertIn("model:", legacy.read_text(encoding="utf-8"))
        self.assertFalse(self.audit.exists())

    def test_uninstall_removes_only_verified_managed_fields(self):
        config = self.base / "opencode.json"
        config.write_text('{"agent":{"build":{"user":"keep"}}}\n', encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 0)
        migrated = parse_jsonc(config)
        migrated["agent"]["reason"]["description"] = "user changed"
        config.write_text(json.dumps(migrated), encoding="utf-8")

        result = self.invoke("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        cleaned = parse_jsonc(config)
        self.assertEqual(cleaned["agent"]["build"], {"user": "keep"})
        self.assertEqual(cleaned["agent"]["reason"]["description"], "user changed")
        self.assertNotIn("model", cleaned["agent"]["reason"])
        self.assertNotIn("review", cleaned["agent"])

    def test_reparse_config_path_is_rejected_without_creating_audit(self):
        target = self.base / "target.jsonc"
        target.write_text("{}\n", encoding="utf-8")
        link = self.base / "opencode.jsonc"
        try:
            link.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"reparse", result.stderr.lower())
        self.assertEqual(target.read_text(encoding="utf-8"), "{}\n")
        self.assertFalse(self.audit.exists())

    def test_duplicate_keys_in_config_or_binding_fail_before_mutation(self):
        config = self.base / "opencode.jsonc"
        config_before = b'{"user": {"nested": 1, "nested": 2}}\n'
        config.write_bytes(config_before)
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"duplicate", result.stderr.lower())
        self.assertEqual(config.read_bytes(), config_before)
        self.assertFalse(self.audit.exists())

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        config_before = b'{"user": true}\n'
        config.write_bytes(config_before)
        self.binding.write_bytes(
            b'{"build":"sample/build-v1","build":"sample/other",'
            b'"reason":null,"review":"sample/review-v1"}\n'
        )
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"duplicate", result.stderr.lower())
        self.assertEqual(config.read_bytes(), config_before)
        self.assertFalse(self.audit.exists())

    def test_nested_bom_agent_is_sanitized_but_unowned_named_role_fails(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        helper = self.base / "agents" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(
            b"\xef\xbb\xbf---\nmodel: sample/helper\n---\nbody\n"
        )
        self.assertEqual(self.invoke().returncode, 0)
        self.assertTrue(helper.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertNotIn("model:", helper.read_text(encoding="utf-8-sig"))

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        role = self.base / "agents" / "nested" / "build.md"
        role.parent.mkdir(parents=True)
        role.write_text("---\nmodel: sample/user\n---\n", encoding="utf-8")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"rename", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(role.is_file())

    def test_backup_collision_and_state_reparse_fail_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        collision = self.binding.parent / "migration-backups" / "collision"
        collision.parent.mkdir()
        collision.write_text("occupied", encoding="utf-8")
        result = self.invoke("--backup-id", "collision")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"already exists", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        config.write_bytes(before)
        target = self.base / "outside"
        target.mkdir()
        reparse = self.binding.parent / "migration-backups"
        try:
            reparse.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"reparse", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)

    def test_malformed_nested_frontmatter_fails_before_config_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        helper = self.base / "agents" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"\xef\xbb\xbf---\nmodel: sample/helper\n")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"unterminated", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse(self.audit.exists())

    def test_reparse_agent_tree_is_rejected_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        target = self.base / "outside-agents"
        target.mkdir()
        agents = self.base / "agents"
        agents.mkdir()
        link = agents / "nested"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"reparse", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse(self.audit.exists())


if __name__ == "__main__":
    unittest.main()
