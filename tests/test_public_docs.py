"""Regression checks for the public installation documentation."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicDocumentationTests(unittest.TestCase):
    def test_readme_covers_supported_installation_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in (
            "## 适用场景与边界",
            "## 安装前提",
            "## 安装",
            "## 升级、卸载与回滚",
            "## 验证与故障排查",
            "## 隐私、安全与平台边界",
        ):
            self.assertIn(heading, readme)
        for url in (
            "https://cursor.com/docs/rules",
            "https://cursor.com/docs/skills",
            "https://cursor.com/docs/mcp",
            "https://docs.tavily.com/documentation/mcp",
            "https://github.com/upstash/context7",
            "https://github.com/github/github-mcp-server",
        ):
            self.assertIn(url, readme)
        for text in (
            "R0",
            "R1",
            "R2",
            "每个 Cursor 项目 checkout",
            "continual-learning",
            "Trackio",
            "grill-me",
            "Trellis",
            "Superpowers",
            "git pull --ff-only origin main",
        ):
            self.assertIn(text, readme)

    def test_documented_flags_and_binding_path_match_installers(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        install_ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
        install_sh = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn(".cursor\\agent-workflow-skills\\model-routing.jsonc", readme)
        self.assertIn("$OpenCodeConfigDir", install_ps1)
        self.assertIn("--opencode-config-dir", install_sh)
        self.assertIn("--opencode-config-dir", readme)


if __name__ == "__main__":
    unittest.main()
