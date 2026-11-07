# PID Safety Corrective — independent static RED baseline

**Pre-fix tip:** `f441da40ade699021980ee636388be9eef42b68c`  
**Source:** `MyPC.Attendance/scripts/windows/p02_usb_hf3_candidate_18878.ps1`  
**Suite:** `tests/unit/test_p02_usb_hf3_pid_owner_independent_red.py`  
**Result on baseline:** **5 RED / 0 GREEN** (read-only STATIC source contract; not Windows runtime).

| # | Defect | Assertion |
|---|--------|-----------|
| 1 | `foreach ($pid in …)` collides with automatic `$PID` | `test_stop_loop_never_assigns_readonly_pid_automatic_variable` |
| 2 | Legacy `uvicorn.pid` alone could authorize kill | `test_no_legacy_pid_only_stop_without_launch_metadata` |
| 3 | Optional `listener_creation` via `-and` short-circuit | `test_listener_creation_required_not_optional_when_meta_is_present` |
| 4 | Missing separate `launcher_creation` | `test_launcher_stop_needs_own_creation_stamp_not_child_creation_stamp` |
| 5 | `$venvMarker` / candidate-folder substring kill auth | `test_no_generic_candidate_marker_as_kill_authorization` |

Post-fix: same suite must be **5 GREEN**. Windows PowerShell 5.1 runtime remains owner-gated (`MYPC_OWNER_WINDOWS_USB=1` + `p02_usb_hf3_pid_safety_runtime_tests.ps1`).
