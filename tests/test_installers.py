import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("code-review", "first-principles", "memory-gate", "parallel-dispatch", "research-routing")
PS = shutil.which("powershell") or shutil.which("pwsh")
BASH = shutil.which("bash")
MODELS = ("-OpenCodeBuildModel", "acme/terra", "-OpenCodeReasonModel", "acme/sol", "-OpenCodeReviewModel", "other/glm")
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
    def test_both_configs_fail_before_mutation(self):
        json_path, json_before = self.config("opencode.json", "{}\n")
        jsonc_path, jsonc_before = self.config("opencode.jsonc", "{},\n")
        self.assertNotEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(json_path.read_bytes(), json_before)
        self.assertEqual(jsonc_path.read_bytes(), jsonc_before)
        self.assertFalse((self.opencode / "skills").exists())
    def test_malformed_config_fails_before_mutation(self):
        path, before = self.config("opencode.jsonc", '{"broken":[}\n')
        self.assertNotEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.opencode / "AGENTS.md").exists())
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
        for skill in SKILLS:
            for root in (self.home / ".cursor/skills", self.opencode / "skills", self.home / ".claude/skills"):
                self.assertTrue((root / skill / "SKILL.md").is_file())
        self.assertTrue((self.project / ".cursor/rules/workflow-gate.mdc").is_file())
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
    def test_opencode_models_are_required_before_mutation(self):
        for tool, extra in (("opencode", ()), ("all", ("-Project", str(self.project)))):
            result = self.invoke("install.ps1", tool, *extra)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"opencode models", result.stderr.lower())
            self.assertFalse(self.opencode.exists())
            self.assertFalse((self.home / ".cursor").exists())
    def test_rendered_models_are_exact_and_bundle_reinstall_updates_only_agents(self):
        config, config_before = self.config("opencode.jsonc", '{"user":true,}\n')
        agents = self.opencode / "AGENTS.md"
        agents.write_text("# keep\n", encoding="utf-8")
        self.assertEqual(self.invoke("install.ps1", "opencode", *MODELS).returncode, 0)
        original = {name: (self.opencode / "agents" / f"{name}.md").read_bytes() for name in ("build", "reason", "review")}
        agents_before = agents.read_bytes()
        skill = (self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes()
        custom = self.opencode / "agents" / "custom.md"
        custom.write_bytes(b"user agent\n")
        changed = ("-OpenCodeBuildModel", "acme/terra-2", "-OpenCodeReasonModel", "acme/sol-2", "-OpenCodeReviewModel", "other/glm-2")
        self.assertEqual(self.invoke("install.ps1", "opencode", *changed).returncode, 0)
        for name, model in zip(("build", "reason", "review"), ("acme/terra-2", "acme/sol-2", "other/glm-2")):
            rendered = (self.opencode / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"model: {model}", rendered)
            self.assertNotEqual(rendered.encode(), original[name])
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(agents.read_bytes(), agents_before)
        self.assertEqual((self.opencode / "skills" / "code-review" / "SKILL.md").read_bytes(), skill)
        self.assertEqual(custom.read_bytes(), b"user agent\n")
        self.assertEqual(self.invoke("install.ps1", "opencode", *changed).returncode, 0)
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
    def test_lifecycle_and_config_guards_are_automatic(self):
        result = self.run_bash(r'''
set -euo pipefail
repo="$1"; root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT; export HOME="$root/home"
run() { env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin bash "$@"; }
mkdir -p "$HOME/.config/opencode"; cfg="$HOME/.config/opencode/opencode.jsonc"
printf '%s\n' '// user' '{"中文":"保留",}' > "$cfg"; cp "$cfg" "$root/before"
for _ in 1 2; do run "$repo/install.sh" --tool opencode --opencode-build-model acme/terra --opencode-reason-model acme/sol --opencode-review-model other/glm; done
cmp "$cfg" "$root/before"; test -f "$HOME/.config/opencode/AGENTS.md"
for skill in code-review first-principles memory-gate parallel-dispatch research-routing; do test -f "$HOME/.config/opencode/skills/$skill/SKILL.md"; done
for agent in build reason review; do test -f "$HOME/.config/opencode/agents/$agent.md"; done
for _ in 1 2; do run "$repo/uninstall.sh" --tool opencode; done
cmp "$cfg" "$root/before"; test ! -e "$HOME/.config/opencode/agents/build.md"
rm -rf "$HOME/.config/opencode"; mkdir -p "$HOME/.config/opencode"
printf '{}\n' > "$HOME/.config/opencode/opencode.json"; printf '{}\n' > "$HOME/.config/opencode/opencode.jsonc"
if run "$repo/install.sh" --tool opencode --opencode-build-model acme/terra --opencode-reason-model acme/sol --opencode-review-model other/glm; then exit 1; fi
test ! -e "$HOME/.config/opencode/skills"
rm "$HOME/.config/opencode/opencode.json"; printf '{"broken":[}\n' > "$HOME/.config/opencode/opencode.jsonc"
if run "$repo/install.sh" --tool opencode --opencode-build-model acme/terra --opencode-reason-model acme/sol --opencode-review-model other/glm; then exit 1; fi
test ! -e "$HOME/.config/opencode/AGENTS.md"
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
