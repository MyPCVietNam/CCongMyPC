# PR6 Follow-up — Security Gates

| Gate | Status | Notes |
|------|--------|-------|
| Signed CAMERA_LAB (HMAC + Zulu payload) | Implemented | Camera-bound; pin fail-closed |
| Signed FACE_PILOT | Implemented | Required before AUTO_VALIDATED |
| AUTO_VALIDATED | Fail-closed | Needs AB run + lab + pilot + gallery |
| REAL_CAMERA enrollment bind | Implemented | Immutable camera/config/approval |
| Settings flag bypass | Closed | Flags alone never open enrollment/shadow |
| RTSP IPv4 pin | Implemented | Hostname rejected on LIVE configure |
| Secret store double-write | Hardened | Single `put_camera_secret` + `secret_ref` |
| Physical CAMERA_LAB PASS | **BLOCKED** | No Windows LIVE decode evidence |
| FACE_PILOT physical | **BLOCKED** | No labeled human pilot |
| INSTALLER | **BLOCKED** | Not built/tested on Windows |
| EXIT_VERIFICATION | **BLOCKED** | Unchanged |

Threat residuals: physical camera still unverified; Windows NTFS ACL audit not executed here; synthetic inference in CI is labeled DEMO_SYNTHETIC, not production evidence.
