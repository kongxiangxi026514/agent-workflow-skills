import json, os, shutil, subprocess, tempfile, unittest
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
    def invoke(self, script, tool, *extra):
        return subprocess.run(
            [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / script), "-Tool", tool, *extra],
            cwd=ROOT, env=self.env, capture_output=True, check=False,
        )
    def assert_agents(self):
        for name in ("build", "reason", "review"):
            self.assertTrue((self.opencode / "agents" / f"{name}.md").read_bytes().startswith(b"---"))
    @property
    def binding(self):
        return self.opencode / "agent-workflow-skills" / "model-routing.jsonc"
    def test_json_config_is_byte_preserved_and_native_agents_install(self):
        path, before = self.config("opencode.json", '{"user":{"中文":"保留"}}\n')
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assert_agents()
    def test_jsonc_comments_and_trailing_commas_are_byte_preserved(self):
        path, before = self.config(
            "opencode.jsonc", '// 用户注释\n{/* block */"user":{"中文":"保留",},}\n'
        )
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.opencode / "opencode.json").exists())
        self.assert_agents()
    def test_both_configs_are_ignored_and_byte_preserved(self):
        json_path, json_before = self.config("opencode.json", "{}\n")
        jsonc_path, jsonc_before = self.config("opencode.jsonc", "{broken jsonc\n")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(json_path.read_bytes(), json_before)
        self.assertEqual(jsonc_path.read_bytes(), jsonc_before)
        self.assert_agents()
    def test_malformed_main_config_does_not_block_or_mutate_install(self):
        path, before = self.config("opencode.jsonc", '{"broken":[}\n')
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assert_agents()
    def test_unmanaged_agent_is_never_overwritten_or_removed(self):
        agent = self.opencode / "agents" / "reason.md"
        rule = self.project / ".cursor/rules/workflow-gate.mdc"
        agent.parent.mkdir(parents=True); rule.parent.mkdir(parents=True)
        agent.write_bytes(b"---\ndescription: user agent\n---\n")
        rule.write_bytes(b"user rule\n")
        before = agent.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "all", "-Project", str(self.project), *MODELS).returncode, 0)
        self.assertEqual(agent.read_bytes(), before)
        self.assertFalse((self.home / ".cursor").exists())
        self.assertEqual(self.invoke("uninstall.ps1", "all", "-Project", str(self.project)).returncode, 0)
        self.assertEqual(agent.read_bytes(), before)
        self.assertEqual(rule.read_bytes(), b"user rule\n")
    def test_cursor_requires_project_before_mutation(self):
        self.assertNotEqual(self.invoke("install.ps1", "cursor").returncode, 0)
        self.assertFalse((self.home / ".cursor").exists())
    def test_full_lifecycle_is_automatic_idempotent_and_utf8(self):
        cfg, before = self.config("opencode.jsonc", '{"路径":"用户保留",}\n')
        agents = self.opencode / "AGENTS.md"
        agents.write_text("# 用户内容\n", encoding="utf-8")
        for _ in range(2):
            result = self.invoke("install.ps1", "all", "-Project", str(self.project), *MODELS)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn("用户", result.stdout.decode("utf-8"))
        self.assertEqual(cfg.read_bytes(), before)
        self.assertEqual(agents.read_text(encoding="utf-8").count("BEGIN agent-workflow-skills spine"), 1)
        self.assertFalse(agents.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assert_agents()
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
        self.assertEqual(cfg.read_bytes(), before)
        self.assertIn("用户内容", agents.read_text(encoding="utf-8"))
        self.assertNotIn("BEGIN agent-workflow-skills spine", agents.read_text(encoding="utf-8"))
        self.assertTrue(custom.is_file())
        self.assertFalse((self.opencode / "agents/build.md").exists())
        self.assertFalse((self.opencode / "agents/reason.md").exists())
        self.assertFalse(self.binding.exists())

    def test_v3_profile_defaults_are_platform_specific_and_owned(self):
        self.assertEqual(
            self.invoke("install.ps1", "all", "-Project", str(self.project), *MODELS).returncode,
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
        args = ("-Project", str(self.project), *MODELS)
        self.assertEqual(self.invoke("install.ps1", "cursor", *args).returncode, 0)
        rule = self.project / ".cursor/rules/workflow-gate.mdc"
        rule.write_text("manual edit\n", encoding="utf-8")
        before = rule.read_bytes()
        result = self.invoke("install.ps1", "cursor", *args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"drift", result.stderr.lower())
        self.assertEqual(rule.read_bytes(), before)

    def test_opencode_models_are_required_before_mutation(self):
        for tool, extra in (("opencode", ()), ("all", ("-Project", str(self.project)))):
            result = self.invoke("install.ps1", tool, *extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"model binding", result.stderr.lower())
            self.assertFalse(self.opencode.exists())
            self.assertFalse((self.home / ".cursor").exists())
    def test_binding_creation_edit_refresh_and_reason_null_fallback(self):
        config, config_before = self.config("opencode.jsonc", '{"user":true,}\n')
        agents = self.opencode / "AGENTS.md"
        agents.write_text("# keep\n", encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode", "-BuildModel", "acme/terra", "-ReviewModel", "other/glm").returncode, 0)
        binding_text = self.binding.read_text(encoding="utf-8")
        self.assertIn('"reason": null', binding_text)
        self.assertIn("model: acme/terra", (self.opencode / "agents/reason.md").read_text(encoding="utf-8"))
        original = {name: (self.opencode / "agents" / f"{name}.md").read_bytes() for name in ("build", "reason", "review")}
        agents_before = agents.read_bytes()
        skill = (self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes()
        custom = self.opencode / "agents" / "custom.md"
        custom.write_bytes(b"user agent\n")
        self.binding.write_text('{"build":"acme/terra-2","reason":"acme/sol-2","review":"other/glm-2"}\n', encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        for name, model in zip(("build", "reason", "review"), ("acme/terra-2", "acme/sol-2", "other/glm-2")):
            rendered = (self.opencode / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"model: {model}", rendered)
            self.assertNotEqual(rendered.encode(), original[name])
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(agents.read_bytes(), agents_before)
        self.assertEqual((self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes(), skill)
        self.assertEqual(custom.read_bytes(), b"user agent\n")
        self.assertEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertTrue((self.opencode / "agent-workflow-skills/install-state.json").is_file())
    def test_review_model_cannot_equal_build_or_reason_before_mutation(self):
        invalid = ("-OpenCodeBuildModel", "acme/terra", "-OpenCodeReasonModel", "acme/sol", "-OpenCodeReviewModel", "acme/terra")
        result = self.invoke("install.ps1", "opencode", *invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"review", result.stderr.lower())
        self.assertFalse(self.opencode.exists())
    def test_orphan_marker_fails_loud_before_install_or_uninstall_mutation(self):
        agents = self.opencode / "AGENTS.md"
        agents.parent.mkdir(parents=True)
        agents.write_text("# before\n<!-- BEGIN agent-workflow-skills spine -->\n# user after\n", encoding="utf-8")
        before = agents.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(agents.read_bytes(), before)
        self.assertFalse((self.opencode / "skills").exists())
        self.assertNotEqual(self.invoke("uninstall.ps1", "opencode").returncode, 0)
        self.assertEqual(agents.read_bytes(), before)
    def test_unowned_skill_refuses_without_creating_binding(self):
        skill = self.opencode / "skills/code-review/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("user-owned\n", encoding="utf-8")
        result = self.invoke("install.ps1", "opencode", *MODELS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(skill.read_text(encoding="utf-8"), "user-owned\n")
        self.assertFalse(self.binding.exists())
        shutil.rmtree(skill.parent)
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        marker = skill.parent / ".agent-workflow-skills-owned"
        marker.unlink()
        skill.write_text("user replacement\n", encoding="utf-8")
        before = skill.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(skill.read_bytes(), before)
        self.assertEqual(self.invoke("uninstall.ps1", "opencode").returncode, 0)
        self.assertEqual(skill.read_bytes(), before)
    def test_config_dir_override_and_failed_refresh_are_safe(self):
        custom = self.home / "自定义配置"
        args = ("-OpenCodeConfigDir", str(custom), *MODELS)
        self.assertEqual(self.invoke("install.ps1", "opencode", *args).returncode, 0)
        binding = custom / "agent-workflow-skills/model-routing.jsonc"
        agent = custom / "agents/build.md"
        before = agent.read_bytes()
        binding.write_text('{"build":"acme/terra","reason":null,"review":"acme/terra"}', encoding="utf-8")
        self.assertNotEqual(self.invoke("install.ps1", "opencode", "-OpenCodeConfigDir", str(custom)).returncode, 0)
        self.assertEqual(agent.read_bytes(), before)
        state = json.loads((custom / "agent-workflow-skills/install-state.json").read_text(encoding="utf-8"))
        self.assertIn("agents/build.md", state["owned_sha256"])
        self.assertEqual(self.invoke("uninstall.ps1", "opencode", "-OpenCodeConfigDir", str(custom)).returncode, 0)
        self.assertFalse(agent.exists())
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
    def test_lifecycle_binding_override_and_main_configs_are_untouched(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
cfgdir="$root/配置"; mkdir -p "$cfgdir"; printf '{}\n' > "$cfgdir/opencode.json"; printf '{bad\n' > "$cfgdir/opencode.jsonc"
cp "$cfgdir/opencode.json" "$root/json"; cp "$cfgdir/opencode.jsonc" "$root/jsonc"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --build-model acme/terra --review-model other/glm
cmp "$cfgdir/opencode.json" "$root/json"; cmp "$cfgdir/opencode.jsonc" "$root/jsonc"
test -f "$cfgdir/agents/build.md"; grep -q 'model: acme/terra' "$cfgdir/agents/reason.md"
binding="$cfgdir/agent-workflow-skills/model-routing.jsonc"
printf '%s\n' '{"build":"acme/new","reason":"acme/sol","review":"other/new"}' > "$binding"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir"
grep -q 'model: acme/new' "$cfgdir/agents/build.md"
run "$repo/uninstall.sh" --tool opencode --opencode-config-dir "$cfgdir"
test ! -e "$cfgdir/agents/build.md"; test ! -e "$binding"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
    def test_empty_bash_profile_is_rejected_before_mutation(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
cfgdir="$root/config"; mkdir -p "$cfgdir"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --profile= --build-model acme/terra --review-model other/glm; then exit 1; fi
test ! -e "$cfgdir/agents/build.md"; test ! -e "$cfgdir/agent-workflow-skills/install-state.json"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
    def test_bash_profiles_default_override_and_owned_spine_drift(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
project="$root/project"; cfgdir="$root/opencode"; mkdir -p "$project" "$cfgdir"
run "$repo/install.sh" --tool cursor --project "$project" --build-model acme/terra --review-model other/glm
grep -q 'profile=lean' "$project/.cursor/rules/workflow-gate.mdc"
run "$repo/install.sh" --tool cursor --project "$project" --profile=balanced
grep -q 'profile=balanced' "$project/.cursor/rules/workflow-gate.mdc"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --build-model acme/terra --review-model other/glm
agents="$cfgdir/AGENTS.md"; grep -q 'profile=balanced' "$agents"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --profile=lean
grep -q 'profile=lean' "$agents"
run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir"
grep -q 'profile=balanced' "$agents"
cp "$agents" "$root/invalid.before"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --profile=foo; then exit 1; fi
cmp "$agents" "$root/invalid.before"
sed -i '/END agent-workflow-skills spine/i tampered generated policy' "$agents"
cp "$agents" "$root/agents.before"; cp "$cfgdir/agents/build.md" "$root/build.before"
if run "$repo/install.sh" --tool opencode --opencode-config-dir "$cfgdir" --profile=lean; then exit 1; fi
cmp "$agents" "$root/agents.before"; cmp "$cfgdir/agents/build.md" "$root/build.before"
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
if run "$repo/install.sh" --tool opencode --opencode-build-model acme/terra --opencode-reason-model acme/sol --opencode-review-model other/glm; then exit 1; fi
cmp "$agents" "$root/before"; test ! -e "$HOME/.config/opencode/skills"
if run "$repo/uninstall.sh" --tool opencode; then exit 1; fi
cmp "$agents" "$root/before"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())
