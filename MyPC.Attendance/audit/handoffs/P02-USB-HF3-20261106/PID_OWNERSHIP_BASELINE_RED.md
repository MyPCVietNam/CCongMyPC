# Reproduction notes and tests to add in PR #27

Baseline source: `MyPC.Attendance/scripts/windows/p02_usb_hf3_candidate_18878.ps1` at HEAD `2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc`.

Known failing source contracts:

1. In Start, the socket owner is treated as valid only if `OwningProcess -eq $proc.Id`; Windows venv Python can launch a real Python interpreter as a child.
2. Start health regex accepts `startup_phase=(READY|FAIL)`; FAIL must never be Start PASS.
3. A broad `catch {}` in the health loop swallows the ownership exception thrown in the same try block; result becomes a misleading generic health failure.
4. Stop/Update use launcher PID metadata, not a durable, verified real listener PID identity. Stale/reused PIDs must never be killed.

Minimal RED/positive matrices to implement (Windows PowerShell 5.1, prefer injected/mocked OS interfaces):

| Scenario | Expected |
|---|---|
| Parent PID owns loopback listener, exact args, READY | PASS |
| Real child owns loopback listener, parent proof and timestamps valid, READY | PASS |
| `conhost.exe` child owns fake socket | FAIL |
| Stranger serves HTTP 200 on 18878 | FAIL, stranger survives |
| Same name/port but wrong `--app-dir` | FAIL |
| Invalid/reused parent PID or child start time | FAIL |
| Listener owned by unrelated process | FAIL, no kill |
| Ambiguous listeners or ownership race | FAIL |
| Health `startup_phase=FAIL` or `status=degraded` | FAIL |
| Verified real Python child still runs after launcher exit | Stop terminates only proven owned child |
| Start abort with verified child | No orphan |
| Start abort without proof | No kill, explicit BLOCKED remediation |
| Candidate already stopped | Stop is safe and idempotent |
| Update while foreign listener active | FAIL, no foreign kill, DataDir unchanged |
| USB physical frames, 30-minute soak, HMAC | Still BLOCKED |

The owner read-only probe **did not** show an active listener. It proves that venv redirector child topology exists, not that the earlier listener was owned by the previous launch. Require proof at runtime.
