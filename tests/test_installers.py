import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "code-review",
    "first-principles",
    "memory-gate",
    "parallel-dispatch",
    "research-routing",
)
V3_SKILLS = (
    "code-review",
    "first-principles",
    "memory-gate",
    "parallel-dispatch",
    "research-routing",
    "workflow-lifecycle",
)
PS = shutil.which("powershell") or shutil.which("pwsh")
BASH = shutil.which("bash")
MODELS = ("-BuildModel", "acme/terra", "-ReasonModel", "acme/sol", "-ReviewModel", "other/glm")
MIGRATE = ("-MigrateOpenCodeModelConfig",)
CURSOR_MODELS = (
    "-BuildModel", "gpt-5.6-terra-xhigh",
    "-ReasonModel", "gpt-5.6-sol-xhigh",
    "-ReviewModel", "glm-5.2-high",
)
PLATFORM_MODELS = (
    "-CursorBuildModel", "gpt-5.6-terra-xhigh",
    "-CursorReasonModel", "gpt-5.6-sol-xhigh",
    "-CursorReviewModel", "glm-5.2-high",
    "-OpenCodeBuildModel", "huawei/glm5.2",
    "-OpenCodeReasonModel", "huawei/glm5.2",
    "-OpenCodeReviewModel", "huawei/kimik2.7",
)
class InstallerTests(unittest.TestCase):
    def setUp(self):
        if not PS:
            self.skipTest("PowerShell unavailable")
        self.temp = tempfile.TemporaryDirectory()
        self.home, self.project = Path(self.temp.name) / "用户", Path(self.temp.name) / "项目"
        self.home.mkdir(); self.project.mkdir()
        self.env = os.environ | {"HOME": str(self.home), "USERPROFILE": str(self.home)}
    def tearDown(self):
        self.temp.cleanup()
    @property
    def opencode(self):
        return self.home / ".config" / "opencode"
    def config(self, name, content):
        path = self.opencode / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload := content.encode("utf-8"))
        return path, payload
    def invoke(self, script, tool, *extra, env=None):
        return subprocess.run(
            [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / script), "-Tool", tool, *extra],
            cwd=ROOT, env=self.env | (env or {}), capture_output=True, check=False,
        )
    def roles(self, config):
        return json.loads(config.read_text(encoding="utf-8"))["agent"]
    @property
    def binding(self):
        return self.opencode / "agent-workflow-skills" / "model-routing.jsonc"
    def test_json_config_migrates_roles_and_retires_legacy_agents(self):
        path, before = self.config("opencode.json", '{"user":{"中文":"保留"}}\n')
        legacy = self.opencode / "agents" / "build.md"
        legacy.parent.mkdir()
        legacy.write_text(
            "---\nmodel: acme/legacy\n---\n<!-- Managed by agent-workflow-skills. -->\n",
            encoding="utf-8",
        )
        state = self.opencode / "agent-workflow-skills" / "install-state.json"
        state.parent.mkdir()
        state.write_text(
            json.dumps(
                {
                    "bundle": "agent-workflow-skills",
                    "version": 2,
                    "platform": "opencode",
                    "profile": "balanced",
                    "owned_sha256": {
                        "agents/build.md": hashlib.sha256(legacy.read_bytes()).hexdigest()
                    },
                }
            ),
            encoding="utf-8",
        )
        result = self.invoke(
            "install.ps1", "opencode", *MIGRATE,
            "-OpenCodeModelConfig", str(path), *MODELS,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.roles(path)["build"]["model"], "acme/terra")
        self.assertFalse(legacy.exists())
        retired = self.opencode / "agent-workflow-skills/retired-agents/agents/build.md"
        self.assertNotIn("model:", retired.read_text(encoding="utf-8"))
        audit = json.loads((self.opencode / "agent-workflow-skills/opencode-model-migration.json").read_text(encoding="utf-8"))
        entry = next(item for item in audit["files"] if item["path"] == "opencode.json")
        self.assertEqual((self.opencode / "agent-workflow-skills" / entry["backup"]).read_bytes(), before)

    def test_jsonc_comments_preserve_semantics_and_keep_unmanaged_agents(self):
        path, before = self.config(
            "opencode.jsonc", '// 用户注释\n{/* block */"user":{"中文":"保留",},}\n'
        )
        helper = self.opencode / "agents/github-helper.md"
        helper.parent.mkdir()
        helper.write_text("---\nmodel: acme/helper\n---\n", encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS).returncode, 0)
        self.assertEqual(self.roles(path)["reason"]["model"], "acme/sol")
        self.assertIn("model:", helper.read_text(encoding="utf-8"))
        self.assertFalse((self.opencode / "opencode.json").exists())

    def test_singular_agent_root_is_preserved_without_audit_entry(self):
        config, _ = self.config("opencode.jsonc", '{"user":"keep"}\n')
        helper = self.opencode / "agent" / "nested" / "github-helper.md"
        helper.parent.mkdir(parents=True)
        original = "---\nmodel: huawei/glm5.2\n---\n"
        helper.write_text(original, encoding="utf-8")
        result = self.invoke(
            "install.ps1",
            "opencode",
            *MIGRATE,
            "-BuildModel",
            "huawei/glm5.2",
            "-ReviewModel",
            "other/glm",
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(self.roles(config)["build"]["model"], "huawei/glm5.2")
        self.assertIn("model:", helper.read_text(encoding="utf-8"))
        audit = json.loads(
            (self.opencode / "agent-workflow-skills/opencode-model-migration.json").read_text(encoding="utf-8")
        )
        self.assertFalse(
            any(item["path"] == "agent/nested/github-helper.md" for item in audit["files"])
        )

    def test_both_configs_fail_before_any_mutation(self):
        json_path, json_before = self.config("opencode.json", "{}\n")
        jsonc_path, jsonc_before = self.config("opencode.jsonc", "{broken jsonc\n")
        result = self.invoke(
            "install.ps1", "all", "-Project", str(self.project), *MIGRATE, *PLATFORM_MODELS
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json_path.read_bytes(), json_before)
        self.assertEqual(jsonc_path.read_bytes(), jsonc_before)
        self.assertFalse((self.home / ".cursor").exists())

    def test_malformed_main_config_blocks_without_mutating_it(self):
        path, before = self.config("opencode.jsonc", '{"broken":[}\n')
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), before)

    def test_unowned_named_role_is_preserved_and_requires_manual_rename(self):
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        role = self.opencode / "agents" / "nested" / "build.md"
        role.parent.mkdir(parents=True)
        role.write_text("---\nmodel: acme/user\n---\n", encoding="utf-8")
        role_before = role.read_bytes()
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"rename", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(role.read_bytes(), role_before)
        self.assertFalse((self.opencode / "skills").exists())
        self.assertFalse((self.opencode / "AGENTS.md").exists())
        self.assertFalse(self.binding.exists())

    def test_opencode_transaction_failure_or_collision_leaves_no_partial_state(self):
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        result = self.invoke(
            "install.ps1", "opencode", *MIGRATE, *MODELS,
            env={"AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER": "4"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((self.opencode / "skills").exists())
        self.assertFalse((self.opencode / "AGENTS.md").exists())
        self.assertFalse(self.binding.exists())
        self.assertFalse(
            (self.opencode / "agent-workflow-skills/install-state.json").exists()
        )

        self.temp.cleanup()
        self.setUp()
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        collision = self.opencode / "agent-workflow-skills/migration-backups"
        collision.parent.mkdir()
        collision.write_text("not a directory", encoding="utf-8")
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((self.opencode / "skills").exists())
        self.assertFalse((self.opencode / "AGENTS.md").exists())
        self.assertFalse(self.binding.exists())

    def test_all_restores_cursor_when_opencode_fails(self):
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        global_keep = self.home / ".cursor" / "keep.txt"
        project_keep = self.project / ".cursor" / "keep.txt"
        global_keep.parent.mkdir()
        project_keep.parent.mkdir()
        global_keep.write_text("global keep\n", encoding="utf-8")
        project_keep.write_text("project keep\n", encoding="utf-8")
        result = self.invoke(
            "install.ps1",
            "all",
            "-Project",
            str(self.project),
            *MIGRATE,
            *PLATFORM_MODELS,
            env={"AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER": "4"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(global_keep.read_text(encoding="utf-8"), "global keep\n")
        self.assertEqual(project_keep.read_text(encoding="utf-8"), "project keep\n")
        self.assertFalse((self.home / ".cursor" / "skills").exists())
        self.assertFalse((self.project / ".cursor" / "rules").exists())
        self.assertFalse((self.home / ".claude").exists())

    def test_all_restores_earlier_targets_when_claude_fails(self):
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        result = self.invoke(
            "install.ps1",
            "all",
            "-Project",
            str(self.project),
            *MIGRATE,
            *PLATFORM_MODELS,
            env={"AGENT_WORKFLOW_TEST_FAIL_PLATFORM": "claude"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((self.project / ".cursor").exists())
        self.assertFalse((self.home / ".cursor").exists())
        self.assertFalse((self.home / ".claude").exists())
        for model in ("huawei/glm5.2", "huawei/kimik2.7"):
            self.assertNotIn(model.encode(), result.stdout + result.stderr)

    def test_opencode_requires_explicit_migration_before_all_mutation(self):
        result = self.invoke("install.ps1", "all", "-Project", str(self.project), *PLATFORM_MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"migration", result.stderr.lower())
        self.assertFalse((self.home / ".cursor").exists())
    def test_cursor_requires_project_before_mutation(self):
        self.assertNotEqual(self.invoke("install.ps1", "cursor").returncode, 0)
        self.assertFalse((self.home / ".cursor").exists())

    def test_forged_cursor_markers_fail_before_install_or_uninstall_mutation(self):
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("forged skill\n", encoding="utf-8")
        (skill.parent / ".agent-workflow-skills-owned").write_text(
            "agent-workflow-skills\n", encoding="utf-8"
        )
        rule = self.project / ".cursor" / "rules" / "workflow-gate.mdc"
        rule.parent.mkdir(parents=True)
        rule.write_text("<!-- Managed by agent-workflow-skills. -->\nforged rule\n", encoding="utf-8")
        skill_before, rule_before = skill.read_bytes(), rule.read_bytes()
        result = self.invoke("install.ps1", "cursor", "-Project", str(self.project), *CURSOR_MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"global skill ownership", result.stderr.lower())
        self.assertEqual(skill.read_bytes(), skill_before)
        self.assertEqual(rule.read_bytes(), rule_before)
        self.assertFalse((self.project / ".cursor" / "agent-workflow-skills").exists())
        result = self.invoke("uninstall.ps1", "cursor", "-Project", str(self.project))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_bytes(), skill_before)
        self.assertEqual(rule.read_bytes(), rule_before)

        self.temp.cleanup()
        self.setUp()
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("forged skill only\n", encoding="utf-8")
        (skill.parent / ".agent-workflow-skills-owned").write_text(
            "agent-workflow-skills\n", encoding="utf-8"
        )
        before = skill.read_bytes()
        result = self.invoke("install.ps1", "cursor", "-Project", str(self.project), *CURSOR_MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_bytes(), before)
        self.assertFalse((self.project / ".cursor").exists())

    def test_cursor_global_skills_support_independent_projects_and_reject_drift(self):
        project_b = Path(self.temp.name) / "项目-b"
        project_b.mkdir()
        args_a = ("-Project", str(self.project), *CURSOR_MODELS)
        args_b = ("-Project", str(project_b), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_a).returncode, 0)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_b).returncode, 0)
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        self.assertTrue(skill.is_file())
        state_a = self.project / ".cursor" / "agent-workflow-skills" / "install-state.json"
        state_b = project_b / ".cursor" / "agent-workflow-skills" / "install-state.json"
        self.assertTrue(state_a.is_file())
        self.assertTrue(state_b.is_file())
        binding_a = self.project / ".cursor" / "agent-workflow-skills" / "model-routing.jsonc"
        binding_b = project_b / ".cursor" / "agent-workflow-skills" / "model-routing.jsonc"
        self.assertEqual(binding_a.read_bytes(), binding_b.read_bytes())

        project_a_before = state_a.read_bytes()
        project_b_before = state_b.read_bytes()
        binding_b_before = binding_b.read_bytes()
        skill.write_text("tampered global skill\n", encoding="utf-8")
        result = self.invoke("install.ps1", "cursor", *args_b)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"global skill", result.stderr.lower())
        self.assertEqual(state_a.read_bytes(), project_a_before)
        self.assertEqual(state_b.read_bytes(), project_b_before)
        self.assertEqual(binding_b.read_bytes(), binding_b_before)
        self.assertEqual(skill.read_text(encoding="utf-8"), "tampered global skill\n")

    def test_cursor_binding_edit_refreshes_state_without_touching_shared_skills(self):
        project_b = Path(self.temp.name) / "项目-b"
        project_b.mkdir()
        args_a = ("-Project", str(self.project), *CURSOR_MODELS)
        args_b = ("-Project", str(project_b), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_a).returncode, 0)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_b).returncode, 0)
        binding_a = self.project / ".cursor" / "agent-workflow-skills" / "model-routing.jsonc"
        state_a = self.project / ".cursor" / "agent-workflow-skills" / "install-state.json"
        binding_b = project_b / ".cursor" / "agent-workflow-skills" / "model-routing.jsonc"
        state_b = project_b / ".cursor" / "agent-workflow-skills" / "install-state.json"
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        binding_a_before = binding_a.read_bytes()
        state_a_before = state_a.read_bytes()
        state_b_before = state_b.read_bytes()
        skill_before = skill.read_bytes()

        binding_b.write_text(
            json.dumps(
                {
                    "build": "composer-2.5-fast",
                    "reason": "cursor-grok-4.5-high-fast",
                    "review": "glm-5.2-high",
                    "families": {
                        "build": "composer-2.5",
                        "reason": "cursor-grok-4.5",
                        "review": "glm-5.2",
                    },
                }
            ) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_b).returncode, 0)

        binding = json.loads(binding_b.read_text(encoding="utf-8").split("\n", 1)[1])
        state = json.loads(state_b.read_text(encoding="utf-8"))
        self.assertEqual(binding["build"], "composer-2.5-fast")
        self.assertEqual(binding["families"]["reason"], "cursor-grok-4.5")
        self.assertEqual(
            state["owned_sha256"]["model-routing.jsonc"],
            hashlib.sha256(binding_b.read_bytes()).hexdigest(),
        )
        self.assertNotEqual(state_b.read_bytes(), state_b_before)
        self.assertEqual(binding_a.read_bytes(), binding_a_before)
        self.assertEqual(state_a.read_bytes(), state_a_before)
        self.assertEqual(skill.read_bytes(), skill_before)

    def test_invalid_cursor_binding_fails_before_any_write(self):
        args = ("-Project", str(self.project), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        bundle = self.project / ".cursor" / "agent-workflow-skills"
        binding = bundle / "model-routing.jsonc"
        state = bundle / "install-state.json"
        rule = self.project / ".cursor" / "rules" / "workflow-gate.mdc"
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        binding.write_text(
            '{"build":"composer-2.5-fast","reason":null,"review":"glm-5.2-high",'
            '"families":{"build":"composer-2.5","reason":null,"review":"bad family!"}}\n',
            encoding="utf-8",
        )
        binding_before = binding.read_bytes()
        state_before = state.read_bytes()
        rule_before = rule.read_bytes()
        skill_before = skill.read_bytes()

        result = self.invoke("install.ps1", "cursor", *args)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(binding.read_bytes(), binding_before)
        self.assertEqual(state.read_bytes(), state_before)
        self.assertEqual(rule.read_bytes(), rule_before)
        self.assertEqual(skill.read_bytes(), skill_before)

    def test_cursor_binding_reparse_fails_ownership_preflight(self):
        args = ("-Project", str(self.project), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        bundle = self.project / ".cursor" / "agent-workflow-skills"
        binding = bundle / "model-routing.jsonc"
        state = bundle / "install-state.json"
        rule = self.project / ".cursor" / "rules" / "workflow-gate.mdc"
        skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        external = Path(self.temp.name) / "external-binding.jsonc"
        external.write_bytes(binding.read_bytes())
        binding.unlink()
        try:
            binding.symlink_to(external)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        state_before = state.read_bytes()
        rule_before = rule.read_bytes()
        skill_before = skill.read_bytes()

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "verify_cursor_ownership.py"),
                "--state",
                str(state),
                "--rules",
                str(rule.parent),
                "--skills",
                str(self.home / ".cursor" / "skills"),
                "--bundle",
                str(bundle),
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"regular non-reparse", result.stdout + result.stderr)
        self.assertEqual(state.read_bytes(), state_before)
        self.assertEqual(rule.read_bytes(), rule_before)
        self.assertEqual(skill.read_bytes(), skill_before)

    def test_cursor_uninstall_allows_a_valid_edited_binding(self):
        args = ("-Project", str(self.project), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        bundle = self.project / ".cursor" / "agent-workflow-skills"
        binding = bundle / "model-routing.jsonc"
        binding.write_text(
            '{"build":"composer-2.5-fast","reason":null,"review":"glm-5.2-high",'
            '"families":{"build":"composer-2.5","reason":null,"review":"glm-5.2"}}\n',
            encoding="utf-8",
        )

        result = self.invoke("uninstall.ps1", "cursor", "-Project", str(self.project))

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertFalse(binding.exists())
        self.assertFalse((bundle / "install-state.json").exists())
        self.assertFalse((self.project / ".cursor" / "rules" / "workflow-gate.mdc").exists())
        self.assertTrue((self.home / ".cursor" / "skills" / "code-review" / "SKILL.md").is_file())

    def test_cursor_uninstall_preserves_shared_skills_until_explicit_removal(self):
        project_b = Path(self.temp.name) / "项目-b"
        project_b.mkdir()
        args_a = ("-Project", str(self.project), *CURSOR_MODELS)
        args_b = ("-Project", str(project_b), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_a).returncode, 0)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args_b).returncode, 0)
        global_skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        custom_skill = self.home / ".cursor" / "skills" / "custom" / "SKILL.md"
        custom_skill.parent.mkdir()
        custom_skill.write_text("user skill\n", encoding="utf-8")
        self.assertEqual(
            self.invoke("uninstall.ps1", "cursor", "-Project", str(self.project)).returncode,
            0,
        )
        self.assertTrue(global_skill.is_file())
        self.assertTrue(custom_skill.is_file())
        self.assertTrue((project_b / ".cursor" / "rules" / "workflow-gate.mdc").is_file())
        self.assertTrue((project_b / ".cursor" / "agent-workflow-skills" / "model-routing.jsonc").is_file())
        self.assertEqual(
            self.invoke("install.ps1", "cursor", *args_b).returncode, 0
        )
        self.assertEqual(
            self.invoke("uninstall.ps1", "cursor", "-Project", str(self.project)).returncode,
            0,
        )
        self.assertTrue(global_skill.is_file())
        self.assertEqual(
            self.invoke(
                "uninstall.ps1",
                "cursor",
                "-Project",
                str(project_b),
                "-RemoveGlobalSkills",
            ).returncode,
            0,
        )
        self.assertFalse(global_skill.exists())
        self.assertTrue(custom_skill.is_file())

    def test_tampered_global_skill_blocks_explicit_removal_without_project_mutation(self):
        args = ("-Project", str(self.project), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        global_skill = self.home / ".cursor" / "skills" / "code-review" / "SKILL.md"
        global_skill.write_text("tampered\n", encoding="utf-8")
        state = self.project / ".cursor" / "agent-workflow-skills" / "install-state.json"
        rule = self.project / ".cursor" / "rules" / "workflow-gate.mdc"
        state_before, rule_before = state.read_bytes(), rule.read_bytes()
        result = self.invoke(
            "uninstall.ps1",
            "cursor",
            "-Project",
            str(self.project),
            "-RemoveGlobalSkills",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"global skill", result.stderr.lower())
        self.assertEqual(global_skill.read_text(encoding="utf-8"), "tampered\n")
        self.assertEqual(state.read_bytes(), state_before)
        self.assertEqual(rule.read_bytes(), rule_before)

    def test_all_uses_isolated_platform_bindings_and_installs_resolver(self):
        result = self.invoke(
            "install.ps1", "all", "-Project", str(self.project), *MIGRATE, *PLATFORM_MODELS
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        cursor_root = self.project / ".cursor" / "agent-workflow-skills"
        cursor_binding = json.loads(
            (cursor_root / "model-routing.jsonc").read_text(encoding="utf-8").split("\n", 1)[1]
        )
        opencode_binding = json.loads(
            self.binding.read_text(encoding="utf-8").split("\n", 1)[1]
        )
        self.assertEqual(cursor_binding["build"], "gpt-5.6-terra-xhigh")
        self.assertEqual(cursor_binding["review"], "glm-5.2-high")
        self.assertEqual(opencode_binding["build"], "huawei/glm5.2")
        self.assertEqual(opencode_binding["review"], "huawei/kimik2.7")
        self.assertNotEqual(cursor_binding, opencode_binding)
        for root in (cursor_root, self.opencode / "agent-workflow-skills"):
            resolver = root / "dispatch_resolver.py"
            self.assertTrue(resolver.is_file())
            state = json.loads((root / "install-state.json").read_text(encoding="utf-8"))
            self.assertIn("dispatch_resolver.py", state["owned_sha256"])
        config = self.opencode / "opencode.jsonc"
        self.assertEqual(self.roles(config)["build"]["model"], "huawei/glm5.2")
        self.assertFalse((self.opencode / "agents/build.md").exists())
        audit = (self.opencode / "agent-workflow-skills/opencode-model-migration.json").read_text(encoding="utf-8")
        state_text = (self.opencode / "agent-workflow-skills/install-state.json").read_text(encoding="utf-8")
        for model in ("huawei/glm5.2", "huawei/kimik2.7"):
            self.assertNotIn(model, audit)
            self.assertNotIn(model, state_text)
            self.assertNotIn(model.encode(), result.stdout + result.stderr)
        self.assertFalse((self.home / ".claude/agent-workflow-skills/model-routing.jsonc").exists())
        self.assertEqual(
            self.invoke("uninstall.ps1", "all", "-Project", str(self.project)).returncode,
            0,
        )
        for root in (cursor_root, self.opencode / "agent-workflow-skills"):
            self.assertFalse((root / "dispatch_resolver.py").exists())
            self.assertFalse((root / "validate_jsonc.py").exists())
    def test_full_lifecycle_is_automatic_idempotent_and_utf8(self):
        cfg, before = self.config("opencode.jsonc", '{"路径":"用户保留",}\n')
        agents = self.opencode / "AGENTS.md"
        agents.write_text("# 用户内容\n", encoding="utf-8")
        for _ in range(2):
            result = self.invoke("install.ps1", "all", "-Project", str(self.project), *MIGRATE, *PLATFORM_MODELS)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("用户", result.stdout.decode("utf-8"))
        self.assertEqual(self.roles(cfg)["build"]["model"], "huawei/glm5.2")
        self.assertEqual(agents.read_text(encoding="utf-8").count("BEGIN agent-workflow-skills spine"), 1)
        self.assertFalse(agents.read_bytes().startswith(b"\xef\xbb\xbf"))
        for skill in V3_SKILLS:
            for root in (self.home / ".cursor/skills", self.opencode / "skills"):
                self.assertTrue((root / skill / "SKILL.md").is_file())
        for skill in V3_SKILLS:
            self.assertTrue((self.home / ".claude/skills" / skill / "SKILL.md").is_file())
        self.assertTrue((self.project / ".cursor/rules/workflow-gate.mdc").is_file())
        self.assertTrue((self.project / ".cursor/rules/model-routing.mdc").is_file())
        self.assertFalse(self.binding.read_bytes().startswith(b"\xef\xbb\xbf"))
        custom = self.opencode / "skills/custom/SKILL.md"
        custom.parent.mkdir(parents=True); custom.write_text("用户技能\n", encoding="utf-8")
        for _ in range(2):
            self.assertEqual(self.invoke("uninstall.ps1", "all", "-Project", str(self.project)).returncode, 0)
        self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["路径"], "用户保留")
        remaining_roles = json.loads(cfg.read_text(encoding="utf-8"))["agent"]
        self.assertTrue(all("model" not in role for role in remaining_roles.values()))
        self.assertIn("用户内容", agents.read_text(encoding="utf-8"))
        self.assertNotIn("BEGIN agent-workflow-skills spine", agents.read_text(encoding="utf-8"))
        self.assertTrue(custom.is_file())
        self.assertFalse((self.opencode / "agents/build.md").exists())
        self.assertFalse((self.opencode / "agents/reason.md").exists())
        self.assertFalse(self.binding.exists())

    def test_v3_profile_defaults_are_platform_specific_and_owned(self):
        self.assertEqual(
            self.invoke("install.ps1", "all", "-Project", str(self.project), *MIGRATE, *PLATFORM_MODELS).returncode,
            0,
        )
        cursor_rule = self.project / ".cursor/rules/workflow-gate.mdc"
        opencode_spine = self.opencode / "AGENTS.md"
        self.assertIn("profile=lean", cursor_rule.read_text(encoding="utf-8"))
        self.assertIn("profile=balanced", opencode_spine.read_text(encoding="utf-8"))
        for state_path, expected_profile in (
            (self.project / ".cursor/agent-workflow-skills/install-state.json", "lean"),
            (self.opencode / "agent-workflow-skills/install-state.json", "balanced"),
        ):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["profile"], expected_profile)
            self.assertIn("workflow-gate.mdc", state["policy_owned_sha256"])
            if state["platform"] == "opencode":
                self.assertRegex(state["spine_block_sha256"], r"^[0-9a-f]{64}$")
        skill = self.opencode / "skills/workflow-lifecycle/SKILL.md"
        self.assertIn("GENERATED; policy_id=P01", skill.read_text(encoding="utf-8"))

    def test_claude_installs_generated_v3_policy_and_blocks_drift(self):
        self.assertEqual(self.invoke("install.ps1", "claude").returncode, 0)
        claude = self.home / ".claude"
        adapter = ROOT / "policy-v3/generated/adapters/claude/balanced/CLAUDE.md"
        spine = (claude / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(adapter.read_text(encoding="utf-8"), spine)
        self.assertIn("profile=balanced", spine)
        state = json.loads((claude / "agent-workflow-skills/install-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["platform"], "claude")
        self.assertEqual(state["profile"], "balanced")
        self.assertIn("workflow-gate.mdc", state["policy_owned_sha256"])
        self.assertRegex(state["spine_block_sha256"], r"^[0-9a-f]{64}$")
        for skill in V3_SKILLS:
            self.assertTrue((claude / "skills" / skill / "SKILL.md").is_file())
        skill = claude / "skills/workflow-lifecycle/SKILL.md"
        skill.write_text("manual edit\n", encoding="utf-8")
        result = self.invoke("install.ps1", "claude")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"drift", result.stderr.lower())
        self.assertEqual(skill.read_text(encoding="utf-8"), "manual edit\n")

    def test_claude_refuses_unowned_v3_skill_before_mutation(self):
        skill = self.home / ".claude/skills/code-review/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("user-owned\n", encoding="utf-8")
        result = self.invoke("install.ps1", "claude")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_text(encoding="utf-8"), "user-owned\n")
        self.assertFalse((self.home / ".claude/CLAUDE.md").exists())

    def test_hand_edited_owned_profile_adapter_fails_before_refresh(self):
        args = ("-Project", str(self.project), *CURSOR_MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        rule = self.project / ".cursor/rules/workflow-gate.mdc"
        rule.write_text("manual edit\n", encoding="utf-8")
        before = rule.read_bytes()
        result = self.invoke("install.ps1", "cursor", *args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ownership", result.stderr.lower())
        self.assertEqual(rule.read_bytes(), before)

    def test_opencode_models_are_required_before_mutation(self):
        for tool, extra in (("opencode", ()), ("all", ("-Project", str(self.project)))):
            result = self.invoke("install.ps1", tool, *extra, *MIGRATE)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"model binding", result.stderr.lower())
            self.assertFalse(self.opencode.exists())
            self.assertFalse((self.home / ".cursor").exists())
    def test_binding_creation_edit_refresh_and_reason_null_fallback(self):
        config, config_before = self.config("opencode.jsonc", '{"user":true,}\n')
        agents = self.opencode / "AGENTS.md"
        agents.write_text("# keep\n", encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MIGRATE, "-BuildModel", "acme/terra", "-ReviewModel", "other/glm").returncode, 0)
        binding_text = self.binding.read_text(encoding="utf-8")
        self.assertIn('"reason": null', binding_text)
        self.assertEqual(self.roles(config)["reason"]["model"], "acme/terra")
        agents_before = agents.read_bytes()
        skill = (self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes()
        custom = self.opencode / "agents" / "custom.md"
        custom.parent.mkdir()
        custom.write_bytes(b"user agent\n")
        self.binding.write_text('{"build":"acme/terra-2","reason":"acme/sol-2","review":"other/glm-2"}\n', encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MIGRATE).returncode, 0)
        for name, model in zip(("build", "reason", "review"), ("acme/terra-2", "acme/sol-2", "other/glm-2")):
            self.assertEqual(self.roles(config)[name]["model"], model)
        self.assertEqual(self.roles(config).get("custom"), None)
        self.assertEqual(agents.read_bytes(), agents_before)
        self.assertEqual((self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes(), skill)
        self.assertEqual(custom.read_bytes(), b"user agent\n")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MIGRATE).returncode, 0)
        self.assertTrue((self.opencode / "agent-workflow-skills/install-state.json").is_file())
    def test_review_model_cannot_equal_build_or_reason_before_mutation(self):
        invalid = ("-OpenCodeBuildModel", "acme/terra", "-OpenCodeReasonModel", "acme/sol", "-OpenCodeReviewModel", "acme/terra")
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"review", result.stderr.lower())
        self.assertFalse(self.opencode.exists())
    def test_orphan_marker_fails_loud_before_install_or_uninstall_mutation(self):
        agents = self.opencode / "AGENTS.md"
        agents.parent.mkdir(parents=True)
        agents.write_text("# before\n<!-- BEGIN agent-workflow-skills spine -->\n# user after\n", encoding="utf-8")
        before = agents.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS).returncode, 0)
        self.assertEqual(agents.read_bytes(), before)
        self.assertFalse((self.opencode / "skills").exists())
        self.assertNotEqual(self.invoke("uninstall.ps1", "opencode").returncode, 0)
        self.assertEqual(agents.read_bytes(), before)

    def test_forged_complete_spine_marker_requires_state_provenance(self):
        agents = self.opencode / "AGENTS.md"
        agents.parent.mkdir(parents=True)
        agents.write_text(
            "# user\n<!-- BEGIN agent-workflow-skills spine -->\n"
            "forged\n<!-- END agent-workflow-skills spine -->\n",
            encoding="utf-8",
        )
        before = agents.read_bytes()
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"spine", result.stderr.lower())
        self.assertEqual(agents.read_bytes(), before)
        self.assertFalse(self.binding.exists())
        result = self.invoke("uninstall.ps1", "opencode")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(agents.read_bytes(), before)

    def test_tampered_spine_uninstall_preserves_opencode_state(self):
        config, _ = self.config("opencode.jsonc", '{"user":"keep"}\n')
        self.assertEqual(
            self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS).returncode, 0
        )
        agents = self.opencode / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8").replace(
                "<!-- END agent-workflow-skills spine -->",
                "tampered\n<!-- END agent-workflow-skills spine -->",
            ),
            encoding="utf-8",
        )
        config_before = config.read_bytes()
        state = self.opencode / "agent-workflow-skills" / "install-state.json"
        state_before = state.read_bytes()
        agents_before = agents.read_bytes()
        result = self.invoke("uninstall.ps1", "opencode")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"provenance", result.stderr.lower())
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(state.read_bytes(), state_before)
        self.assertEqual(agents.read_bytes(), agents_before)
        self.assertTrue((self.opencode / "skills" / "code-review" / "SKILL.md").is_file())

    def test_unowned_skill_refuses_without_creating_binding(self):
        skill = self.opencode / "skills/code-review/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("user-owned\n", encoding="utf-8")
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_text(encoding="utf-8"), "user-owned\n")
        self.assertFalse(self.binding.exists())
        shutil.rmtree(skill.parent)
        self.assertEqual(self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS).returncode, 0)
        marker = skill.parent / ".agent-workflow-skills-owned"
        marker.unlink()
        skill.write_text("user replacement\n", encoding="utf-8")
        before = skill.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "opencode", *MIGRATE).returncode, 0)
        self.assertEqual(skill.read_bytes(), before)
        self.assertNotEqual(self.invoke("uninstall.ps1", "opencode").returncode, 0)
        self.assertEqual(skill.read_bytes(), before)

    def test_forged_owned_skill_marker_and_state_hash_fail_before_mutation(self):
        config, before = self.config("opencode.jsonc", '{"user":"keep"}\n')
        skill = self.opencode / "skills" / "code-review" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("forged\n", encoding="utf-8")
        (skill.parent / ".agent-workflow-skills-owned").write_text(
            "agent-workflow-skills\n", encoding="utf-8"
        )
        state = self.opencode / "agent-workflow-skills" / "install-state.json"
        state.parent.mkdir()
        state.write_text(
            json.dumps(
                {
                    "bundle": "agent-workflow-skills",
                    "version": 3,
                    "platform": "opencode",
                    "profile": "balanced",
                    "owned_sha256": {"skills/code-review/SKILL.md": "0" * 64},
                }
            ),
            encoding="utf-8",
        )
        result = self.invoke("install.ps1", "opencode", *MIGRATE, *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ownership", result.stderr.lower())
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(skill.read_text(encoding="utf-8"), "forged\n")
        self.assertFalse((self.opencode / "AGENTS.md").exists())
        self.assertFalse(self.binding.exists())
    def test_config_dir_override_and_failed_refresh_are_safe(self):
        custom = self.home / "自定义配置"
        args = ("-OpenCodeConfigDir", str(custom), *MIGRATE, *MODELS)
        self.assertEqual(self.invoke("install.ps1", "opencode", *args).returncode, 0)
        binding = custom / "agent-workflow-skills/model-routing.jsonc"
        config = custom / "opencode.jsonc"
        before = config.read_bytes()
        binding.write_text('{"build":"acme/terra","reason":null,"review":"acme/terra"}', encoding="utf-8")
        self.assertNotEqual(self.invoke("install.ps1", "opencode", "-OpenCodeConfigDir", str(custom), *MIGRATE).returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        state = json.loads((custom / "agent-workflow-skills/install-state.json").read_text(encoding="utf-8"))
        self.assertNotIn("agents/build.md", state["owned_sha256"])
        self.assertEqual(self.invoke("uninstall.ps1", "opencode", "-OpenCodeConfigDir", str(custom)).returncode, 0)
        remaining_roles = json.loads(config.read_text(encoding="utf-8"))["agent"]
        self.assertTrue(all("model" not in role for role in remaining_roles.values()))
    def test_generated_runtime_policy_contains_roles_not_model_ids(self):
        generated = ROOT / "policy-v3/generated"
        files = sorted((generated / "adapters").rglob("*")) + sorted((generated / "skills").rglob("SKILL.md"))
        files = [path for path in files if path.is_file()]
        self.assertTrue(files)
        text = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for role in ("build", "reason", "review"):
            self.assertIn(role, text)
        for forbidden in ("gpt-5.6-", "glm-5.2-max", "huawei/"):
            self.assertNotIn(forbidden, text.lower())

    def test_active_markdown_and_cursor_rule_never_hardcode_models(self):
        cursor_rule = (ROOT / "cursor/model-routing.mdc").read_text(encoding="utf-8")
        self.assertNotRegex(cursor_rule, r"(?m)^model\s*:")
        self.assertNotIn("gpt-5.6", cursor_rule)
        self.assertNotIn("glm-5.2", cursor_rule)
        for root_name in ("agent", "agents"):
            agents = ROOT / "opencode" / root_name
            for path in agents.rglob("*.md") if agents.exists() else ():
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?m)^model\s*:")

class JsoncValidatorTests(unittest.TestCase):
    def test_block_comment_between_tokens_does_not_merge_values(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as file:
            file.write(b'{"broken":[1/* comment */2]}\n')
            path = Path(file.name)
        try:
            result = subprocess.run(["python", str(ROOT / "tools/validate_jsonc.py"), str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        finally:
            path.unlink()

    def test_duplicate_keys_are_rejected_at_nested_levels(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as file:
            file.write(b'{"outer":{"duplicate":1,"duplicate":2}}\n')
            path = Path(file.name)
        try:
            result = subprocess.run(["python", str(ROOT / "tools/validate_jsonc.py"), str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"duplicate", result.stderr.lower())
        finally:
            path.unlink()

@unittest.skipUnless(BASH, "bash unavailable")
class BashInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([BASH, "-c", 'wslpath -a "$1"', "bash", str(ROOT)], capture_output=True, check=False)
        if result.returncode:
            raise unittest.SkipTest("bash cannot access repository")
        cls.root = result.stdout.decode().strip()
    def run_bash(self, script):
        return subprocess.run([BASH, "-s", "--", self.root], input=script.encode(), capture_output=True, check=False)
    def test_bash_migrates_selected_jsonc_with_backup_and_uninstall(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
cfgdir="$root/配置"; mkdir -p "$cfgdir"; printf '%s\n' '// 用户注释' '{"用户":"保留",}' > "$cfgdir/opencode.jsonc"
cp "$cfgdir/opencode.jsonc" "$root/jsonc"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config \
  --opencode-model-config "$cfgdir/opencode.jsonc" --build-model acme/terra --review-model other/glm
grep -q '"用户": "保留"' "$cfgdir/opencode.jsonc"; grep -q '"model": "acme/terra"' "$cfgdir/opencode.jsonc"
test -f "$cfgdir/agent-workflow-skills/migration-backups/"*/opencode.jsonc
cmp "$cfgdir/agent-workflow-skills/migration-backups/"*/opencode.jsonc "$root/jsonc"
mode="$(stat -c %a "$cfgdir/opencode.jsonc")"; test $((8#$mode & 077)) -eq 0
backup_mode="$(stat -c %a "$cfgdir/agent-workflow-skills/migration-backups/"*/opencode.jsonc)"; test $((8#$backup_mode & 077)) -eq 0
test ! -e "$cfgdir/agents/build.md"
binding="$cfgdir/agent-workflow-skills/model-routing.jsonc"
printf '%s\n' '{"build":"acme/new","reason":"acme/sol","review":"other/new"}' > "$binding"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config
grep -q '"model": "acme/new"' "$cfgdir/opencode.jsonc"
run "$repo/uninstall.sh" --tool opencode --opencode-config-dir "$cfgdir"
test ! -e "$binding"; ! grep -q '"model": "acme/new"' "$cfgdir/opencode.jsonc"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_singular_agent_root_is_preserved_without_audit_entry(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
cfg="$root/opencode"; mkdir -p "$cfg/agent/nested"; printf '%s\n' '{"user":"keep"}' > "$cfg/opencode.jsonc"
printf '%s\n' '---' 'model: huawei/glm5.2' '---' > "$cfg/agent/nested/github-helper.md"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfg" --migrate-opencode-model-config --build-model huawei/glm5.2 --review-model other/glm
grep -q '^model:' "$cfg/agent/nested/github-helper.md"
grep -q '"model": "huawei/glm5.2"' "$cfg/opencode.jsonc"
! test -e "$cfg/agent-workflow-skills/migration-backups/"*/agent/nested/github-helper.md
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_transaction_failure_leaves_no_partial_opencode_state(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
cfgdir="$root/config"; mkdir -p "$cfgdir"; printf '%s\n' '{"user":"keep"}' > "$cfgdir/opencode.jsonc"; cp "$cfgdir/opencode.jsonc" "$root/before"
if env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER=4 \
  bash "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config \
  --build-model acme/terra --review-model other/glm; then exit 1; fi
cmp "$cfgdir/opencode.jsonc" "$root/before"
test ! -e "$cfgdir/skills"; test ! -e "$cfgdir/AGENTS.md"
test ! -e "$cfgdir/agent-workflow-skills/model-routing.jsonc"
test ! -e "$cfgdir/agent-workflow-skills/install-state.json"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_all_restores_prior_platforms_on_later_failures(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
project="$root/project"; config="$root/opencode"; mkdir -p "$project" "$config"
printf '%s\n' '{"user":"keep"}' > "$config/opencode.jsonc"; cp "$config/opencode.jsonc" "$root/before"
common=(--tool all --project "$project" --opencode-config-dir "$config" --migrate-opencode-model-config
  --cursor-build-model gpt-5.6-terra-xhigh --cursor-review-model glm-5.2-high
  --opencode-build-model acme/terra --opencode-review-model other/glm)
if env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin AGENT_WORKFLOW_OPENCODE_TRANSACTION_FAIL_AFTER=4 \
  bash "$repo/install.sh" "${common[@]}"; then exit 1; fi
cmp "$config/opencode.jsonc" "$root/before"; test ! -e "$project/.cursor"; test ! -e "$HOME/.cursor"; test ! -e "$HOME/.claude"
if env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin AGENT_WORKFLOW_TEST_FAIL_PLATFORM=claude \
  bash "$repo/install.sh" "${common[@]}"; then exit 1; fi
cmp "$config/opencode.jsonc" "$root/before"; test ! -e "$project/.cursor"; test ! -e "$HOME/.cursor"; test ! -e "$HOME/.claude"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_tampered_spine_uninstall_is_atomic(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
cfg="$root/opencode"; mkdir -p "$cfg"; printf '%s\n' '{"user":"keep"}' > "$cfg/opencode.jsonc"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfg" --migrate-opencode-model-config --build-model acme/terra --review-model other/glm
sed -i '/END agent-workflow-skills spine/i tampered' "$cfg/AGENTS.md"
cp "$cfg/opencode.jsonc" "$root/config.before"; cp "$cfg/agent-workflow-skills/install-state.json" "$root/state.before"; cp "$cfg/AGENTS.md" "$root/agents.before"
if run "$repo/uninstall.sh" --tool opencode --opencode-config-dir "$cfg"; then exit 1; fi
cmp "$cfg/opencode.jsonc" "$root/config.before"; cmp "$cfg/agent-workflow-skills/install-state.json" "$root/state.before"; cmp "$cfg/AGENTS.md" "$root/agents.before"
test -f "$cfg/skills/code-review/SKILL.md"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_cursor_skills_are_shared_across_projects(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
a="$root/project-a"; b="$root/project-b"; mkdir -p "$a" "$b"
run "$repo/install.sh" --tool cursor --project "$a" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high
run "$repo/install.sh" --tool cursor --project "$b" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high
test -f "$HOME/.cursor/skills/code-review/SKILL.md"; test -f "$a/.cursor/agent-workflow-skills/install-state.json"; test -f "$b/.cursor/agent-workflow-skills/install-state.json"
cp "$a/.cursor/agent-workflow-skills/install-state.json" "$root/a.before"; cp "$b/.cursor/agent-workflow-skills/install-state.json" "$root/b.before"
printf 'tampered\n' > "$HOME/.cursor/skills/code-review/SKILL.md"
if run "$repo/install.sh" --tool cursor --project "$b" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high; then exit 1; fi
cmp "$a/.cursor/agent-workflow-skills/install-state.json" "$root/a.before"; cmp "$b/.cursor/agent-workflow-skills/install-state.json" "$root/b.before"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_cursor_global_skill_removal_requires_opt_in(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
a="$root/project-a"; b="$root/project-b"; mkdir -p "$a" "$b"
run "$repo/install.sh" --tool cursor --project "$a" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high
run "$repo/install.sh" --tool cursor --project "$b" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high
mkdir -p "$HOME/.cursor/skills/custom"; printf 'user skill\n' > "$HOME/.cursor/skills/custom/SKILL.md"
run "$repo/uninstall.sh" --tool cursor --project "$a"
test -f "$HOME/.cursor/skills/code-review/SKILL.md"; test -f "$b/.cursor/rules/workflow-gate.mdc"
run "$repo/uninstall.sh" --tool cursor --project "$b" --remove-global-skills
test ! -e "$HOME/.cursor/skills/code-review"; test -f "$HOME/.cursor/skills/custom/SKILL.md"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_all_keeps_cursor_and_opencode_models_isolated(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
project="$root/project"; config="$root/opencode"; mkdir -p "$project" "$config"
run "$repo/install.sh" --tool all --project "$project" --opencode-config-dir "$config" --migrate-opencode-model-config \
  --cursor-build-model gpt-5.6-terra-xhigh --cursor-reason-model gpt-5.6-sol-xhigh \
  --cursor-review-model glm-5.2-high --opencode-build-model huawei/glm5.2 \
  --opencode-reason-model huawei/glm5.2 --opencode-review-model huawei/kimik2.7
grep -q '"build": "gpt-5.6-terra-xhigh"' "$project/.cursor/agent-workflow-skills/model-routing.jsonc"
grep -q '"build": "huawei/glm5.2"' "$config/agent-workflow-skills/model-routing.jsonc"
grep -q '"model": "huawei/glm5.2"' "$config/opencode.jsonc"
test -f "$project/.cursor/agent-workflow-skills/dispatch_resolver.py"
test -f "$config/agent-workflow-skills/dispatch_resolver.py"
test ! -e "$HOME/.claude/agent-workflow-skills/model-routing.jsonc"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
    def test_empty_bash_profile_is_rejected_before_mutation(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
cfgdir="$root/config"; mkdir -p "$cfgdir"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config --profile= --build-model acme/terra --review-model other/glm; then exit 1; fi
test ! -e "$cfgdir/opencode.jsonc"; test ! -e "$cfgdir/agent-workflow-skills/install-state.json"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
    def test_bash_profiles_default_override_and_owned_spine_drift(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
project="$root/project"; cfgdir="$root/opencode"; mkdir -p "$project" "$cfgdir"
run "$repo/install.sh" --tool cursor --project "$project" --build-model gpt-5.6-terra-xhigh --review-model glm-5.2-high
grep -q 'profile=lean' "$project/.cursor/rules/workflow-gate.mdc"
run "$repo/install.sh" --tool cursor --project "$project" --profile=balanced
grep -q 'profile=balanced' "$project/.cursor/rules/workflow-gate.mdc"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config --build-model acme/terra --review-model other/glm
agents="$cfgdir/AGENTS.md"; grep -q 'profile=balanced' "$agents"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config --profile=lean
grep -q 'profile=lean' "$agents"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config
grep -q 'profile=balanced' "$agents"
cp "$agents" "$root/invalid.before"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config --profile=foo; then exit 1; fi
cmp "$agents" "$root/invalid.before"
sed -i '/END agent-workflow-skills spine/i tampered generated policy' "$agents"
cp "$agents" "$root/agents.before"; cp "$cfgdir/opencode.jsonc" "$root/config.before"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --migrate-opencode-model-config --profile=lean; then exit 1; fi
cmp "$agents" "$root/agents.before"; cmp "$cfgdir/opencode.jsonc" "$root/config.before"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_bash_claude_uses_generated_v3_adapter_and_drift_guard(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
run "$repo/install.sh" --tool claude
claude="$HOME/.claude"; grep -q 'policy_id=P00' "$claude/CLAUDE.md"
grep -q 'profile=balanced' "$claude/CLAUDE.md"; test -f "$claude/skills/workflow-lifecycle/SKILL.md"
test -f "$claude/agent-workflow-skills/install-state.json"
printf 'manual edit\n' > "$claude/skills/workflow-lifecycle/SKILL.md"
cp "$claude/skills/workflow-lifecycle/SKILL.md" "$root/before"
if run "$repo/install.sh" --tool claude; then exit 1; fi
cmp "$claude/skills/workflow-lifecycle/SKILL.md" "$root/before"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
    def test_orphan_marker_preserves_content_for_install_and_uninstall(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
mkdir -p "$HOME/.config/opencode"; agents="$HOME/.config/opencode/AGENTS.md"
printf '%s\n' '# before' '<!-- BEGIN agent-workflow-skills spine -->' '# user after' > "$agents"; cp "$agents" "$root/before"
if run "$repo/install.sh" --tool opencode --migrate-opencode-model-config --opencode-build-model acme/terra --opencode-reason-model acme/sol --opencode-review-model other/glm; then exit 1; fi
cmp "$agents" "$root/before"; test ! -e "$HOME/.config/opencode/skills"
if run "$repo/uninstall.sh" --tool opencode; then exit 1; fi
cmp "$agents" "$root/before"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
