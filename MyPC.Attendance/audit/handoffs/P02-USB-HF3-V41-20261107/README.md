# HF3 PID Safety V4.1 COMPLETE AUDIT

PR #27 residual fail-closed corrective. **READY_FOR_INDEPENDENT_REAUDIT** only — not owner Start approval.

| Archive | Name |
|---------|------|
| CHANGED | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-HF3-V41.zip` |
| FULL | `MyPC.Attendance-FULL-SOURCE-HF3-V41.zip` |
| EVIDENCE | `MYPC-HF3-V41-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE | `MYPC-HF3-V41-COMPLETE-AUDIT.zip` |

## Pins

| Role | SHA |
|------|-----|
| Baseline V4 tip (R1–R8 RED) | `7c6a324da7a22c704b33a8ad1b0319099f38f1da` |
| Feature tip (Actions 4/4) | `979349f52c755474ab3cecd7ab8c701bf43acd5b` |
| COMPLETE download tip | `7137baea75e994e34b9df6d33939c7fe2ab97c56` |
| Prior V4 COMPLETE SHA256 | `068ee217304cd17ce366b768882b84297b7e89617955186ef1b9405d1881bf48` |

Do **not** mix prior V4 superseded PENDING digests (`d9c465…`) with this package.

## Verified COMPLETE (HTTP 200 + SHA256 OK)

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/7137baea75e994e34b9df6d33939c7fe2ab97c56/MyPC.Attendance/audit/handoffs/P02-USB-HF3-V41-20261107/MYPC-HF3-V41-COMPLETE-AUDIT.zip

| Archive | SHA256 |
|---------|--------|
| COMPLETE | `ebcaf153c4eafa3c46646f2bd93f85c91b8823e9f8d64fb19619d8d1062b7654` (4049024 bytes) |
| CHANGED | `cc4679e708b3643c3213c195518f9ba4b9de7ebb73a95a1d41a6f697d75fba5e` |
| FULL | `2151a8e5847df33292352793e87304de2058cdaa6bea324b17276d5941a7f94b` |
| EVIDENCE | `adf522e7aaaa5c88d51da1adfb0256979ff1e917e87306ff6c9f6f176949ab06` |

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/7137baea75e994e34b9df6d33939c7fe2ab97c56/MyPC.Attendance/audit/handoffs/P02-USB-HF3-V41-20261107/MYPC-HF3-V41-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-HF3-V41-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected: `ebcaf153c4eafa3c46646f2bd93f85c91b8823e9f8d64fb19619d8d1062b7654`

CODE_GATE: https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42366402413 (`979349f`)

Physical gates **BLOCKED**.
