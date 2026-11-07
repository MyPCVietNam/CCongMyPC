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

    def test_rejects_python_dash_c_with_uvicorn_tokens(self):
        cmd = (
            r'C:\Python\python.exe -c "import time; time.sleep(60)" '
            r"-m uvicorn app.main:app --host 127.0.0.1 --port 18878 "
            r"--app-dir C:\HF3\backend"
        )
        self.assertFalse(self.module.uvicorn_cmdline_matches(cmd, port=18878, backend=r"C:\HF3\backend"))

    def test_start_free_port_probes_launch_meta(self):
        start = HF3.read_text(encoding="utf-8-sig").split('  "Start" {', 1)[1].split('  "Stop" {', 1)[0]
        free = start.split("# Stale metadata with free port", 1)[1].split("$launchNonce", 1)[0]
        self.assertTrue("Get-Hf3LaunchMetaState" in free or "Read-Hf3LaunchMeta" in free)
        self.assertIn("Get-Win32ProcessById", free)
        self.assertIn("EXIT_START_STALE_LAUNCHER", free)
        self.assertIn("EXIT_START_INVALID_LAUNCH_META", free)

    def test_runtime_has_no_qualified_real_stop_process(self):
        if not RUNTIME.exists():
            self.skipTest("HF3 Windows runtime script absent")
        s = RUNTIME.read_text(encoding="utf-8-sig", errors="replace")
        self.assertNotRegex(s, r"(?i)Microsoft\.PowerShell\.Management\\Stop-Process")

    def test_v4_invalid_meta_and_unknown_probes_fail_closed(self):
        s = HF3.read_text(encoding="utf-8-sig", errors="replace")
        self.assertIn("function Get-Hf3LaunchMetaState", s)
        self.assertIn("EXIT_STOP_INVALID_LAUNCH_META", s)
        self.assertIn("EXIT_UPDATE_INVALID_LAUNCH_META", s)
        self.assertIn("EXIT_UPDATE_STALE_LISTENER", s)
        self.assertIn("EXIT_PROCESS_PROBE_UNKNOWN", s)
        self.assertIn("EXIT_TCP_PROBE_UNKNOWN", s)
        getproc = s.split("function Get-Win32ProcessById", 1)[1].split("function Split-Hf3WindowsCommandLine", 1)[0]
        self.assertNotIn("-ErrorAction SilentlyContinue", getproc)
        gettcp = s.split("function Get-Hf3PortListenerOwnerPids", 1)[1].split("function Resolve-Hf3ListenerOwnership", 1)[0]
        self.assertNotIn("-ErrorAction SilentlyContinue", gettcp)

    def test_v4_appdir_spaces_quoted_in_formatter(self):
        backend = r"C:\Users\Test User\p02-usb-hf3-candidate\src\backend"
        line = self.module.format_uvicorn_process_arguments(backend=backend, port=18878)
        self.assertIn('"C:\\Users\\Test User\\p02-usb-hf3-candidate\\src\\backend"', line)

if __name__ == "__main__":
    unittest.main()
