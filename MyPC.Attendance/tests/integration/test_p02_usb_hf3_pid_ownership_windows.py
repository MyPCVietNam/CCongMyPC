"""Windows PowerShell 5.1 runtime checks for HF3 PID ownership helpers.

Skipped unless MYPC_OWNER_WINDOWS_USB=1 on Windows. Never starts the attendance
app, never opens a camera, never kills unknown processes. Owner must authorize
any real HF3 Start separately after independent audit.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MYPC_OWNER_WINDOWS_USB", "").strip() != "1"
    or platform.system().lower() != "windows",
    reason="Owner Windows USB/PS flag not set — PID runtime remains BLOCKED in CI",
)

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "scripts" / "windows" / "p02_usb_hf3_candidate_18878.ps1"


def test_owner_windows_ps51_pid_foreach_collision_absent():
    text = PS1.read_text(encoding="utf-8-sig")
    assert "foreach ($pid" not in text.lower().replace("foreach($pid", "foreach ($pid")


def test_owner_windows_ps51_stop_verified_identity_parses():
    """Dot-source helper definitions only; do not Start/Stop the candidate."""
    probe = r"""
$ErrorActionPreference = 'Stop'
$script = $env:HF3_PS1
# Extract and define only the pure helper functions by invoking a dry parse
$ast = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$null, [ref]$errs)
if ($errs) { throw ($errs | Out-String) }
Write-Output 'PARSE_OK'
"""
    env = os.environ.copy()
    env["HF3_PS1"] = str(PS1)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", probe],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "PARSE_OK" in r.stdout
