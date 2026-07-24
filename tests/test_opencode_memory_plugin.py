"""Static compatibility tests for the optional OpenCode local-memory plugin."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "verify_opencode_memory_plugin.py"
PLUGIN = ROOT / "opencode" / "agent-workflow-memory.ts"
CONTRACT = ROOT / "opencode" / "local-memory-contract.json"


def load_probe():
    spec = importlib.util.spec_from_file_location("verify_opencode_memory_plugin", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenCodeMemoryPluginTests(unittest.TestCase):
    def test_static_contract_matches_local_plugin(self):
        probe = load_probe()
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

        probe.verify_source(PLUGIN, contract)

    def test_plugin_uses_only_transient_message_capture_and_bounded_context(self):
        text = PLUGIN.read_text(encoding="utf-8")

        self.assertIn("MAX_TRANSIENT_CHARS", text)
        self.assertIn("MAX_CONTEXT_TOKENS", text)
        self.assertIn('invoke("capture"', text)
        self.assertIn('"telemetry"', text)
        self.assertNotIn('"tool.execute.after"', text)
        self.assertNotIn("console.log(", text)

    def test_probe_rejects_missing_or_incomplete_runtime_binary(self):
        result = subprocess.run(
            [sys.executable, str(PROBE), "--require-runtime"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"opencode-bin", result.stderr)

    def test_probe_rejects_a_plugin_missing_a_required_hook(self):
        probe = load_probe()
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            plugin = Path(temp) / "plugin.ts"
            plugin.write_text('const hook = "chat.message"\n', encoding="utf-8")

            with self.assertRaisesRegex(probe.ContractError, "required hook"):
                probe.verify_source(plugin, contract)

    def test_prepare_install_stages_memory_only_when_explicitly_enabled(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "stage"
            binding = Path(temp) / "binding.jsonc"
            command = [
                sys.executable,
                str(ROOT / "tools" / "prepare_install.py"),
                str(stage),
                str(binding),
                "opencode",
                "balanced",
                "sample/build",
                "-",
                "sample/review",
                "--enable-local-memory",
            ]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue((stage / "local_memory.py").is_file())
            self.assertTrue((stage / "verify_opencode_memory_plugin.py").is_file())
            self.assertTrue((stage / "plugins" / "agent-workflow-memory.ts").is_file())
            state = json.loads((stage / "install-state.json").read_text(encoding="utf-8"))
            self.assertIn("plugins/agent-workflow-memory.ts", state["owned_sha256"])


if __name__ == "__main__":
    unittest.main()
