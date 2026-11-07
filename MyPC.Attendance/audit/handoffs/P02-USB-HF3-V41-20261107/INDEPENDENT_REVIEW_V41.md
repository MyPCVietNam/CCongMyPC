# Independent residual review — HF3 V4.1

| Field | Value |
|-------|-------|
| Immutable V4 tip (RED) | `7c6a324da7a22c704b33a8ad1b0319099f38f1da` |
| V4.1 feature tip (CI) | `979349f52c755474ab3cecd7ab8c701bf43acd5b` |
| Prior V4 COMPLETE SHA256 | `068ee217304cd17ce366b768882b84297b7e89617955186ef1b9405d1881bf48` |
| Classification | SECURITY_SENSITIVE + WINDOWS_HOST (mocked) |

Independent structural canaries R1–R8 were RED on V4 tip; after V4.1 corrective they are GREEN (8/8) plus injected PowerShell handler scenarios. Physical gates remain BLOCKED. Code-only verdict pending packaging remote verify → READY_FOR_INDEPENDENT_REAUDIT.
