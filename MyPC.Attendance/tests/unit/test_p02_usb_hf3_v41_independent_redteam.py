"""Independent HF3 V4 residual-safety contracts. Strictly READ-ONLY; Python + source assertions.

RED here is a code-level adversarial contract, not an observed Windows-owner incident.
No camera, PowerShell, CIM, TCP, file mutations or process termination are invoked.
"""
import importlib.util
import re
from pathlib import Path

import os
BASE = Path(os.environ.get('HF3_REPO_ROOT') or Path.cwd())
if (BASE / 'MyPC.Attendance' / 'scripts' / 'windows' / 'p02_usb_hf3_candidate_18878.ps1').is_file():
    ROOT = BASE / 'MyPC.Attendance'
elif (BASE / 'scripts' / 'windows' / 'p02_usb_hf3_candidate_18878.ps1').is_file():
    ROOT = BASE
else:
    ROOT = Path(__file__).resolve().parent / 'MyPC.Attendance-FULL-SOURCE-HF3-V4' / 'MyPC.Attendance'
if not (ROOT / 'scripts/windows/p02_usb_hf3_candidate_18878.ps1').is_file():
    raise RuntimeError('Supply HF3_REPO_ROOT pointing to repository root or MyPC.Attendance')
PS = (ROOT/'scripts/windows/p02_usb_hf3_candidate_18878.ps1').read_text(encoding='utf-8-sig')
V4_HARNESS = (ROOT/'scripts/windows/p02_usb_hf3_v4_fail_closed_runtime_tests.ps1').read_text(encoding='utf-8-sig')


def mode(name,next_name):
    return PS.split(f'  "{name}" {{', 1)[1].split(f'  "{next_name}" {{', 1)[0]


def fn(name,next_name):
    return PS.split(f'function {name}',1)[1].split(f'function {next_name}',1)[0]


def test_r1_start_rejects_syntactically_valid_but_invalid_schema_before_metadata_cleanup():
    """Malformed *schema* (not JSON parse error) must not authorize cleanup + Start."""
    start=mode('Start','Stop')
    free=start.split('# Stale metadata with free port',1)[1].split('$launchNonce',1)[0]
    assert 'Get-Hf3LaunchMetaState' in free
    assert 'Test-Hf3LaunchMetaSchema' in free or 'Validate-Hf3LaunchMetaBeforeCleanup' in free, (
        'Start accepts JSON-object meta with invalid schema and 0/absent PIDs as VALID; '
        'then archives+removes meta without complete identity proof')


def test_r2_update_rejects_invalid_schema_before_source_swap():
    update=mode('Update','Preflight')
    free=update.split('# Port free:',1)[1].split('$backupLeaf',1)[0]
    assert 'Get-Hf3LaunchMetaState' in free
    assert 'Test-Hf3LaunchMetaSchema' in free or 'Validate-Hf3LaunchMetaBeforeCleanup' in free, (
        'Update with syntactically parseable invalid-schema meta proceeds to src rename/swap')


def test_r3_stop_checks_saved_listener_when_port_free():
    stop=mode('Stop','Diagnose')
    no_listener=stop.split('# No listener:',1)[1]
    assert re.search(r'(?:Get-Win32ProcessById|Stop-VerifiedHf3Identity)[\s\S]{0,260}(?:listener_pid|listenerPidStop)',no_listener, re.I), (
        'Stop free-port path probes launcher only and removes persisted meta without '
        'checking saved listener PID+creation; an off-port live listener can be orphaned')


def test_r4_update_no_meta_requires_legacy_pid_safety_check():
    update=mode('Update','Preflight')
    free=update.split('# Port free:',1)[1].split('$backupLeaf',1)[0]
    assert '$pidFile' in free, (
        'Update with free port + absent launch meta + legacy uvicorn.pid does not check '
        'whether PID is still live/unverifiable before source swap')


def test_r5_tcp_unknown_cannot_be_downgraded_via_generic_exception_message():
    tcp=fn('Get-Hf3PortListenerOwnerPids','Resolve-Hf3ListenerOwnership')
    broad=re.search(r'No MSFT_NetTCPConnection\|ObjectNotFound\|No matching\|cannot find',tcp,re.I)
    assert not broad, (
        'Broad message substring allowlist can treat provider error e.g. '
        '"Provider timeout: No matching response" as no listener')


def test_r6_python_mirror_refuses_non_python_listener_even_with_matching_argv():
    path=ROOT/'scripts/windows/hf3_pid_ownership.py'
    spec=importlib.util.spec_from_file_location('hf3_residual',path)
    mod=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    actual=mod.kill_authorized(role='listener',expected_creation='2026-11-07T10:00:00Z',live_creation='2026-11-07T10:00:00Z',is_conhost=False,cmdline_ok=True,is_python=False,exe_matches_expected=False)
    assert not actual, 'Python mirror incorrectly AUTHORIZES non-Python listener; diverges from PowerShell stop guard'


def test_r7_v4_behavioral_harness_does_not_cover_main_mode_control_flows():
    # RED if only isolated helpers are tested. This is a coverage contract, not a claim of runtime exploit.
    sources=V4_HARNESS
    assert 'Stop-VerifiedHf3LaunchTree' in sources or 'Invoke-Hf3StopHandler' in sources or 'Invoke-Hf3UpdateHandler' in sources, (
        'V4 PowerShell harness only extracts helper functions; no Start/Stop/Update handler behavior or blocked side effects are exercised')


def test_r8_update_must_validate_both_identities_before_stopping_any_process():
    """Launcher alive + off-port live listener must block without *prior* launcher kill."""
    update=mode('Update','Preflight')
    free=update.split('# Port free:',1)[1].split('$backupLeaf',1)[0]
    probe_loop=free.split('foreach ($rolePidName',1)[1]
    assert 'Stop-VerifiedHf3Identity' not in probe_loop, (
        'Update iterates launcher first: may kill valid launcher before checking saved '
        'listener PID; then throws EXIT_UPDATE_STALE_LISTENER after partial side effect')
