"""Independent hostile tests against real HF3 source: no OS-side effects.

These tests are intentionally RED against the uploaded PID Safety V2 baseline.
That is a release blocker, not an invitation to skip or weaken a test.
"""
from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PSDIR = ROOT / "MyPC.Attendance" / "scripts" / "windows"
HF3 = PSDIR / "p02_usb_hf3_candidate_18878.ps1"
RUNTIME = PSDIR / "p02_usb_hf3_pid_safety_runtime_tests.ps1"
HELPER = PSDIR / "hf3_pid_ownership.py"


@unittest.skipUnless(HF3.exists() and HELPER.exists(), "HF3 feature not in current checkout; guard remains available")
class Hf3Safety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("hf3_pid_ownership_guarded", HELPER)
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.module = module

    def test_rejects_foreign_appdir_even_with_hf3_in_log_config(self):
        target = r"C:\Users\Owner\HF3\MyPC.Attendance\backend"
        foreign = r"C:\other-app\backend"
        cmd = f'python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir "{foreign}" --log-config "{target}"'
        self.assertFalse(self.module.uvicorn_cmdline_matches(cmd, backend=target, port=18878),
                         "Do not accept backend folder merely appearing in --log-config")

    def test_accepts_exact_appdir_positive(self):
        target = r"C:\Users\Owner\HF3\MyPC.Attendance\backend"
        cmd = f'python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir "{target}"'
        self.assertTrue(self.module.uvicorn_cmdline_matches(cmd, backend=target, port=18878))

    def test_rejects_wrong_appdir_with_backend_as_unrelated_token(self):
        target = r"C:\Users\Owner\HF3\MyPC.Attendance\backend"
        cmd = f'python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\\foreign --note "{target}"'
        self.assertFalse(self.module.uvicorn_cmdline_matches(cmd, backend=target, port=18878))

    def test_ps_has_no_substring_backend_authorization(self):
        s = HF3.read_text(encoding="utf-8-sig", errors="replace")
        fn = re.search(r"(?is)function\s+Test-Hf3UvicornCommandLine\b(.{0,3000}?)\bfunction\s+Test-IsPythonProcessName", s)
        self.assertIsNotNone(fn)
        self.assertNotRegex(fn.group(1), r"(?i)\bIndexOf\s*\(\s*\$backendNorm")

    def test_synthetic_does_not_call_fake_numeric_pid_stop(self):
        if not RUNTIME.exists():
            self.skipTest("HF3 Windows runtime script absent")
        s = RUNTIME.read_text(encoding="utf-8-sig", errors="replace")
        self.assertNotRegex(s, r"(?i)\bStop-VerifiedHf3Identity\s+-TargetPid\s+4242\b")

    def test_synthetic_never_executes_real_stop_process(self):
        if not RUNTIME.exists():
            self.skipTest("HF3 Windows runtime script absent")
        s = RUNTIME.read_text(encoding="utf-8-sig", errors="replace")
        self.assertNotRegex(s, r"(?im)^\s*(?:try\s*\{\s*)?Stop-Process\b")

    def test_health_fail_closed(self):
        self.assertFalse(self.module.health_is_start_pass(200, '{"status":"degraded","startup_phase":"FAIL","nested":{"status":"ok","startup_phase":"READY"}}'))
        self.assertTrue(self.module.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}'))

    def test_pid_creation_required(self):
        self.assertFalse(self.module.creation_time_matches("", "2026-11-07T00:00:00Z"))
        self.assertFalse(self.module.creation_time_matches("2026-11-07T00:00:00Z", ""))

if __name__ == "__main__":
    unittest.main()
