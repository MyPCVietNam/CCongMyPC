"""HF3 V4.1 independent read-only residual canaries (expected RED on the V4.1 ZIP).

Usage: HF3_REPO_ROOT=/path/to/repo python independent_v41_residual_canaries.py
No PowerShell execution, camera access, real process operations, or DataDir writes.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import re
import sys
import unittest

base = Path(os.environ.get('HF3_REPO_ROOT') or Path(__file__).parent/'source').resolve()
ROOT = base if (base/'MyPC.Attendance/scripts/windows/p02_usb_hf3_candidate_18878.ps1').exists() else base.parent
SCRIPTS = ROOT/'MyPC.Attendance/scripts/windows'
PS = (SCRIPTS/'p02_usb_hf3_candidate_18878.ps1').read_text(encoding='utf-8-sig')
HARNESS = (SCRIPTS/'p02_usb_hf3_v4_fail_closed_runtime_tests.ps1').read_text(encoding='utf-8-sig')
spec=importlib.util.spec_from_file_location('mypc_hf3_v41_independent', SCRIPTS/'hf3_pid_ownership.py')
helper=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=helper
spec.loader.exec_module(helper)

def mode(name: str, nxt: str) -> str:
    return PS.split(f'  "{name}" {{',1)[1].split(f'  "{nxt}" {{',1)[0]

def contains_pid_consistency_check(segment: str) -> bool:
    # Predicate needs BOTH the pid file and a read/probe/identity check.
    return bool(re.search(r'(?is)(?:Get-Content\s+[^\n]*\$pidFile|Read-Hf3PidRecord\s+[^\n]*\$pidFile|Test-Hf3PidRecord\s+[^\n]*\$pidFile)',segment))

class ResidualSafety(unittest.TestCase):
    def test_r9_prepare_process_guard_before_destructive_source_replace(self):
        before=mode('Prepare','Update').split('Remove-Item -Recurse -Force $srcDir',1)[0]
        self.assertTrue('Get-Hf3PortListenerOwnerPids' in before and 'Get-Hf3LaunchMetaState' in before,
            'R9: Prepare may remove existing src without TCP and PID/meta identity safety gate')

    def test_r9b_prepare_essential_model_inputs_checked_before_deletion(self):
        before=mode('Prepare','Update').split('Remove-Item -Recurse -Force $srcDir',1)[0]
        self.assertIn('Prepare requires -ModelsSourceDir',before,
            'R9b: missing models source can fail after existing source is deleted')

    def test_r10_update_checks_pid_file_even_with_valid_meta(self):
        free=mode('Update','Preflight').split('# Port free:',1)[1].split('$backupLeaf',1)[0]
        before_else=free.split('} elseif (Test-Path -LiteralPath $pidFile)',1)[0]
        self.assertTrue(contains_pid_consistency_check(before_else),
            'R10: Update examines uvicorn.pid only when meta ABSENT, not when VALID')

    def test_r10b_start_checks_pid_file_even_with_valid_meta(self):
        free=mode('Start','Stop').split('# Stale metadata with free port',1)[1].split('$launchNonce',1)[0]
        before_else=free.split('} elseif (Test-Path $pidFile)',1)[0]
        self.assertTrue(contains_pid_consistency_check(before_else),
            'R10b: Start discards uvicorn.pid without consistency verification if meta VALID')

    def test_r11_python_mirror_direct_listener_blank_name_is_unverified(self):
        backend=r'C:\HF3\backend'
        cmd=r'python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend'
        p=helper.ProcessSnap(4242,'',0,cmd,'2026-11-07T00:00:00Z')
        classification,_ = helper.classify_listener_ownership(p,p,{4242:p},port=18878,backend=backend)
        self.assertEqual(classification,helper.REL_UNVERIFIED,
            'R11: helper accepts blank process name as DIRECT unlike production PowerShell')

    def test_r12_real_mode_handler_coverage_not_duplicate_facades(self):
        # Note: There are various valid test architectures; this checks this specific
        # harness does not claim coverage by only defining duplicated handler facades.
        facades=all('function Invoke-Hf3'+name+'Handler' in HARNESS for name in ('Start','Update','Stop'))
        production=all('function Invoke-Hf3'+name+'Handler' in PS for name in ('Start','Update','Stop'))
        extracts_modes=bool(re.search(r'(Extract-ModeText|Extract-SwitchMode|Get-ProductionModeBody)',HARNESS))
        self.assertTrue(not facades or production or extracts_modes,
            'R12: test harness exercises synthetic copied handlers, not production mode branches')

if __name__=='__main__':
    unittest.main(verbosity=2)
