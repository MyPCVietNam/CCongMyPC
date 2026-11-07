"""Pure framework tests: no network, process kill, owner files or cameras."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from quality_guard.check import find_issues

ROOT = Path(__file__).resolve().parents[2]


class FrameworkContract(unittest.TestCase):
    def test_selftest_contract(self):
        self.assertEqual(find_issues(ROOT, strict=False), [])

    def test_hook_restricts_shell_and_fails_closed(self):
        hook = json.loads((ROOT / ".cursor/hooks.json").read_text())
        self.assertEqual(hook["version"], 1)
        self.assertTrue(hook["hooks"]["beforeShellExecution"][0]["failClosed"])

    def test_required_gates_not_mislabeled_as_physical(self):
        rules = (ROOT / "AGENTS.md").read_text()
        self.assertIn("USB_STABILITY_30_MIN", rules)
        self.assertIn("never", rules.lower())

    def test_no_user_data_in_quality_overlay(self):
        # This test scans the guard package itself, not the historical app archive.
        forbidden = (".sqlite", ".sqlite3", ".onnx", ".pem", ".pfx", ".mp4", ".avi")
        for path in ROOT.joinpath("quality_guard").rglob("*"):
            if path.is_file():
                self.assertFalse(path.name.lower().endswith(forbidden), path.as_posix())

if __name__ == "__main__":
    unittest.main()
