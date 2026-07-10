import os, shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("code-review", "first-principles", "memory-gate", "parallel-dispatch", "research-routing")
PS = shutil.which("powershell") or shutil.which("pwsh")
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
        for name in ("build", "review"): self.assertTrue((self.opencode / "agents" / f"{name}.md").read_bytes().startswith(b"---"))
    def test_json_config_is_byte_preserved_and_native_agents_install(self):
        path, before = self.config("opencode.json", '{"user":{"中文":"保留"}}\n')
        self.assertEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assert_agents()
    def test_jsonc_comments_and_trailing_commas_are_byte_preserved(self):
        path, before = self.config(
            "opencode.jsonc", '// 用户注释\n{/* block */"user":{"中文":"保留",},}\n'
        )
        self.assertEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.opencode / "opencode.json").exists())
        self.assert_agents()
    def test_both_configs_fail_before_mutation(self):
        json_path, json_before = self.config("opencode.json", "{}\n")
        jsonc_path, jsonc_before = self.config("opencode.jsonc", "{},\n")
        self.assertNotEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(json_path.read_bytes(), json_before)
        self.assertEqual(jsonc_path.read_bytes(), jsonc_before)
        self.assertFalse((self.opencode / "skills").exists())
    def test_malformed_config_fails_before_mutation(self):
        path, before = self.config("opencode.jsonc", '{"broken":[}\n')
        self.assertNotEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.opencode / "AGENTS.md").exists())
    def test_unmanaged_agent_is_never_overwritten_or_removed(self):
        agent = self.opencode / "agents" / "build.md"
        rule = self.project / ".cursor/rules/workflow-gate.mdc"
        agent.parent.mkdir(parents=True); rule.parent.mkdir(parents=True)
        agent.write_bytes(b"---\ndescription: user agent\n---\n")
        rule.write_bytes(b"user rule\n")
        before = agent.read_bytes()
        self.assertNotEqual(self.invoke("install.ps1", "opencode").returncode, 0)
        self.assertEqual(agent.read_bytes(), before)
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
            result = self.invoke("install.ps1", "all", "-Project", str(self.project))
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
