"""Adversarial contracts for the atomic OpenCode JSON/JSONC role migration."""

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
HELPER = ROOT / "tools" / "migrate_opencode_models.py"


def parse_jsonc(path: Path) -> dict:
    sys.path.insert(0, str(ROOT / "tools"))
    from validate_jsonc import normalize_jsonc

    return json.loads(normalize_jsonc(path.read_text(encoding="utf-8")))


def load_helper():
    sys.path.insert(0, str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location(
        "migrate_opencode_models", HELPER
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
                    "version": 2,
                    "platform": "opencode",
                    "profile": "balanced",
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
        self.assertEqual(
            migrated["agent"]["review"]["permission"],
            {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "lsp": "allow",
                "skill": "allow",
            },
        )
        self.assertIn("model:", helper.read_text(encoding="utf-8"))
        self.assertFalse((agents / "build.md").exists())
        retired = self.base / "agent-workflow-skills" / "retired-agents" / "agents" / "build.md"
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
        self.assertEqual(config.read_bytes(), before, result.stderr.decode("utf-8", "replace"))
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
        self.assertNotIn("model", cleaned["agent"]["review"])
        self.assertNotIn("permission", cleaned["agent"]["review"])

    def test_uninstall_rejects_role_model_drift_without_mutation(self):
        config = self.base / "opencode.json"
        config.write_text("{}\n", encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 0)
        drifted = parse_jsonc(config)
        drifted["agent"]["build"]["model"] = "sample/user-replacement"
        config.write_text(json.dumps(drifted), encoding="utf-8")
        before = config.read_bytes()
        audit_before = self.audit.read_bytes()
        result = self.invoke("--uninstall")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"drift", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(self.audit.read_bytes(), audit_before)

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

    def test_nested_bom_custom_agent_is_preserved_but_unowned_named_role_fails(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        helper = self.base / "agents" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(
            b"\xef\xbb\xbf---\nmodel: sample/helper\n---\nbody\n"
        )
        self.assertEqual(self.invoke().returncode, 0)
        self.assertTrue(helper.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertIn("model:", helper.read_text(encoding="utf-8-sig"))

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

    def test_malformed_custom_frontmatter_is_preserved(self):
        config = self.base / "opencode.jsonc"
        config.write_bytes(b'{"user":"keep"}\n')
        helper = self.base / "agents" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"\xef\xbb\xbf---\nmodel: sample/helper\n")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(helper.read_bytes(), b"\xef\xbb\xbf---\nmodel: sample/helper\n")
        self.assertTrue(self.audit.exists())

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

    def test_duplicate_agent_names_across_roots_fail_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        for root in ("agent", "agents"):
            helper = self.base / root / "nested" / "github-helper.md"
            helper.parent.mkdir(parents=True)
            helper.write_text("---\nmodel: sample/helper\n---\n", encoding="utf-8")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"duplicate", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue((self.base / "agent" / "nested" / "github-helper.md").is_file())
        self.assertTrue((self.base / "agents" / "nested" / "github-helper.md").is_file())

    def test_unowned_named_role_in_singular_root_fails_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        role = self.base / "agent" / "build.md"
        role.parent.mkdir()
        role.write_text("---\nmodel: sample/user\n---\n", encoding="utf-8")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"rename", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(role.is_file())

    def test_custom_agent_frontmatter_is_never_rewritten(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        helper = self.base / "agents" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        helper.write_text(
            "---\n\"model\": sample/double\n'model': sample/single\nMODEL: sample/upper\n"
            "description: helper\npermission:\n  edit: deny\n---\n",
            encoding="utf-8",
        )
        self.assertEqual(self.invoke().returncode, 0)
        sanitized = helper.read_text(encoding="utf-8")
        self.assertIn("model", sanitized.lower())
        self.assertIn("description: helper", sanitized)
        self.assertIn("permission:\n  edit: deny", sanitized)

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)
        helper = self.base / "agents" / "github-helper.md"
        helper.parent.mkdir()
        helper.write_text("---\nmodel: |\n  unsafe\n---\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("model: |", helper.read_text(encoding="utf-8"))

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        config.write_bytes(before)
        helper = self.base / "agents" / "github-helper.md"
        helper.parent.mkdir()
        helper.write_text(
            "---\ndescription: [unterminated\nmodel: sample/helper\n---\n",
            encoding="utf-8",
        )
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("model: sample/helper", helper.read_text(encoding="utf-8"))

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        config.write_bytes(before)
        helper = self.base / "agents" / "github-helper.md"
        helper.parent.mkdir()
        helper.write_text("---\n<<: *shared\n---\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

    def test_existing_role_fields_and_permissions_are_restored(self):
        config = self.base / "opencode.json"
        original = {
            "agent": {
                "build": {
                    "model": "sample/old-build",
                    "mode": "custom",
                    "description": "keep build",
                    "custom": {"nested": True},
                },
                "review": {
                    "model": "sample/old-review",
                    "mode": "custom-review",
                    "description": "keep review",
                    "permission": {"bash": "ask", "prompt": "keep"},
                },
            }
        }
        config.write_text(json.dumps(original), encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 0)
        migrated = parse_jsonc(config)
        self.assertEqual(migrated["agent"]["build"]["mode"], "custom")
        self.assertEqual(migrated["agent"]["build"]["description"], "keep build")
        self.assertEqual(migrated["agent"]["build"]["custom"], {"nested": True})
        self.assertEqual(
            migrated["agent"]["review"]["permission"],
            {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "lsp": "allow",
                "skill": "allow",
            },
        )
        self.assertEqual(migrated["agent"]["reason"]["mode"], "subagent")
        self.binding.write_text(
            json.dumps(
                {
                    "build": "sample/build-v2",
                    "reason": None,
                    "review": "sample/review-v2",
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.invoke().returncode, 0)

        result = self.invoke("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        cleaned = parse_jsonc(config)
        self.assertNotIn("model", cleaned["agent"]["build"])
        self.assertEqual(cleaned["agent"]["build"]["custom"], {"nested": True})
        self.assertEqual(
            cleaned["agent"]["review"]["permission"],
            {"bash": "ask", "prompt": "keep"},
        )

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.json"
        config.write_text(
            json.dumps({"agent": {"review": {"model": "sample/old", "custom": True}}}),
            encoding="utf-8",
        )
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(
            parse_jsonc(config)["agent"]["review"]["permission"],
            {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "lsp": "allow",
                "skill": "allow",
            },
        )
        self.assertTrue(parse_jsonc(config)["agent"]["review"]["custom"])

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.json"
        conflict = copy = {
            "agent": {"review": {"model": "sample/old", "permission": {"edit": "allow"}}}
        }
        config.write_bytes(json.dumps(copy).encode("utf-8"))
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            parse_jsonc(config)["agent"]["review"]["permission"]["*"], "deny"
        )

    def test_audit_never_serializes_model_ids_and_lock_contention_fails_loudly(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        audit_text = self.audit.read_text(encoding="utf-8")
        state_text = (self.binding.parent / "install-state.json").read_text(encoding="utf-8") if (self.binding.parent / "install-state.json").exists() else ""
        for model in ("sample/build-v1", "sample/review-v1"):
            self.assertNotIn(model, audit_text)
            self.assertNotIn(model, state_text)
            self.assertNotIn(model.encode(), result.stdout + result.stderr)

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        before = b"{}\n"
        config.write_bytes(before)
        lock = self.binding.parent / ".opencode-model-migration.lock"
        lock.write_text("held", encoding="utf-8")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"lock", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)

    def test_forged_agent_marker_and_manifest_hash_fail_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b"{}\n"
        config.write_bytes(before)
        agent = self.base / "agents" / "build.md"
        agent.parent.mkdir()
        agent.write_text(
            "---\nmodel: sample/user\n---\n<!-- Managed by agent-workflow-skills. -->\n",
            encoding="utf-8",
        )
        (self.binding.parent / "install-state.json").write_text(
            json.dumps(
                {
                    "bundle": "agent-workflow-skills",
                    "version": 2,
                    "platform": "opencode",
                    "profile": "balanced",
                    "owned_sha256": {"agents/build.md": "0" * 64},
                }
            ),
            encoding="utf-8",
        )
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"bundle-owned", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue(agent.is_file())

    def test_simulated_path_swap_is_detected_before_second_commit_and_rolls_back(self):
        helper = load_helper()
        first = self.base / "first.txt"
        second = self.base / "second.txt"
        first.write_bytes(b"first-before")
        second.write_bytes(b"second-before")
        original_write = helper._write_atomic

        def swap_before_write(path, content, mode=None, guard=None):
            if path == second:
                second.unlink()
                second.write_bytes(b"attacker-replacement")
            return original_write(path, content, mode, guard)

        helper._write_atomic = swap_before_write
        try:
            with self.assertRaises(helper.MigrationError):
                helper._apply_transaction(
                    [
                        helper.Change(first, b"first-before", b"first-after"),
                        helper.Change(second, b"second-before", b"second-after"),
                    ],
                    base=self.base,
                )
        finally:
            helper._write_atomic = original_write
        self.assertEqual(first.read_bytes(), b"first-before")
        self.assertEqual(second.read_bytes(), b"attacker-replacement")

    def test_readonly_roles_are_fail_closed_and_custom_agents_stay_unchanged(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        custom = self.base / "agents" / "project-helper.md"
        custom.parent.mkdir()
        custom_before = (
            b"---\ndescription: project helper\nmodel: sample/custom\n---\n"
            b"Keep this custom agent independent.\n"
        )
        custom.write_bytes(custom_before)

        self.assertEqual(self.invoke().returncode, 0)

        migrated = parse_jsonc(config)
        for role in ("reason", "review"):
            self.assertEqual(
                migrated["agent"][role]["permission"],
                {
                    "*": "deny",
                    "read": "allow",
                    "glob": "allow",
                    "grep": "allow",
                    "list": "allow",
                    "lsp": "allow",
                    "skill": "allow",
                },
            )
        self.assertEqual(custom.read_bytes(), custom_before)

    def test_unchanged_migration_does_not_rewrite_or_create_backup(self):
        config = self.base / "opencode.jsonc"
        config.write_text("{}\n", encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 0)
        before = config.read_bytes()
        audit_before = self.audit.read_bytes()
        backup_root = self.binding.parent / "migration-backups"
        backups_before = sorted(path.relative_to(backup_root) for path in backup_root.rglob("*"))

        self.assertEqual(self.invoke().returncode, 0)

        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(self.audit.read_bytes(), audit_before)
        self.assertEqual(
            sorted(path.relative_to(backup_root) for path in backup_root.rglob("*")),
            backups_before,
        )

    def test_explicit_model_registry_rejects_unavailable_role_before_mutation(self):
        config = self.base / "opencode.jsonc"
        before = b'{"user":"keep"}\n'
        config.write_bytes(before)

        result = self.invoke(
            "--available-model",
            "sample/build-v1",
            "--available-model",
            "sample/review-v1",
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))

        self.temp.cleanup()
        self.setUp()
        config = self.base / "opencode.jsonc"
        config.write_bytes(before)
        result = self.invoke("--available-model", "sample/build-v1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"unavailable", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse(self.audit.exists())

    def test_local_memory_plugin_registration_is_audited_and_reversible(self):
        config = self.base / "opencode.jsonc"
        config.write_text('{"plugin":["existing-plugin"]}\n', encoding="utf-8")

        result = self.invoke("--enable-local-memory")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            parse_jsonc(config)["plugin"],
            ["existing-plugin", "./plugins/agent-workflow-memory.ts"],
        )
        audit = json.loads(self.audit.read_text(encoding="utf-8"))
        self.assertTrue(audit["local_memory_plugin_added"])

        result = self.invoke("--uninstall")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(parse_jsonc(config)["plugin"], ["existing-plugin"])


if __name__ == "__main__":
    unittest.main()
