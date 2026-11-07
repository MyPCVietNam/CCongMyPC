# HF3 PID Safety V4 COMPLETE AUDIT

PR #27 in-place fail-closed corrective. **READY_FOR_INDEPENDENT_REAUDIT** only — not owner Start approval.

| Archive | Name |
|---------|------|
| CHANGED | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-HF3-V4.zip` |
| FULL | `MyPC.Attendance-FULL-SOURCE-HF3-V4.zip` |
| EVIDENCE | `MYPC-HF3-V4-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE | `MYPC-HF3-V4-COMPLETE-AUDIT.zip` |

## Pins (this PACKAGE_META only)

| Role | SHA |
|------|-----|
| Baseline tip (RED custody) | `8dc2dfed68464eb7ba98db6fc4efae90ee3f07a4` |
| Feature tip (Actions 4/4) | `a915445289132cec50466ee616c90baa8d2f0cac` |
| COMPLETE download tip | `289c3d88fc66edb4793ee36f7692cc7572a60c33` |

Historical HF3/Quality Guard COMPLETE digests under `P02-USB-HF3-20261106/` and `QUALITY-GUARD-v1.0/` (and freeze `30d93f1…`) are **prior pins** — do **not** mix with this `PACKAGE_META.json`.

Physical gates remain **BLOCKED**. Do not Prepare/Start/Stop/Update/runtime harness on owner Windows in this phase.

## Verified COMPLETE (HTTP 200 + SHA256 OK)

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/289c3d88fc66edb4793ee36f7692cc7572a60c33/MyPC.Attendance/audit/handoffs/P02-USB-HF3-V4-20261107/MYPC-HF3-V4-COMPLETE-AUDIT.zip

| Archive | SHA256 |
|---------|--------|
| COMPLETE | `068ee217304cd17ce366b768882b84297b7e89617955186ef1b9405d1881bf48` (4038791 bytes) |
| CHANGED | `51ac09cd3720a75b8b7d0787992dd4f5b018815e8cba41769e8e4ebed22a27e4` |
| FULL | `6c37b888ff6592b4342e5e181b03215473b499a4fb1eea09a48f494d1726dc78` |
| EVIDENCE | `96d8e96aab100ca86f876caee6044cce75101c0fca2b80a69001f32777c5b61f` |

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/289c3d88fc66edb4793ee36f7692cc7572a60c33/MyPC.Attendance/audit/handoffs/P02-USB-HF3-V4-20261107/MYPC-HF3-V4-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-HF3-V4-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected: `068ee217304cd17ce366b768882b84297b7e89617955186ef1b9405d1881bf48`

CODE_GATE feature tip (Actions 4/4): `a915445289132cec50466ee616c90baa8d2f0cac` — https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42362887883
