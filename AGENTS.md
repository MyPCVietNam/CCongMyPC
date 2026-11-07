# MyPC Attendance - Mandatory Engineering Contract

Repository source is under `MyPC.Attendance/` (not repository root). The target is a Windows 10/11 offline/local attendance system with EZVIZ RTSP and USB UVC cameras; frontend React/TypeScript and backend Python 3.12/FastAPI. Follow `.cursor/rules/` and the `/mypc-safe-change` skill.

## Before editing
- Identify the precise base branch, current HEAD, dirty files, and affected files. The public `main` may contain only LICENSE while the active app lives on a feature PR. Never infer that `main` contains the application.
- Produce an impact map of API, DB, privacy, process management, migrations, frontend and release evidence. State expected regression tests (including negative cases) and rollback.
- For a bug fix, first demonstrate a failing regression on the baseline, then implement minimal changes and obtain GREEN on the new tip. Do not rewrite unrelated components to make tests pass.
- API contracts must be checked against installed package versions. Windows-specific behavior requires Windows PowerShell 5.1 tests, not only Linux pytest.

## Non-negotiable safety
- Never execute a real process kill, camera start, camera capture, attendance mutation, deletion, registry edit, or system/network configuration from a synthetic test or GitHub-hosted CI. Mock/inject the operating system boundary; `Stop-Process` in a test is not a mock.
- Preserve `127.0.0.1:18876`, `:18877`, EZVIZ/HMAC records, owner secrets, existing DataDirs, biometric data and model weights. HF3 sandbox port is `127.0.0.1:18878`, with separate data. No `Prepare` on an already-prepared owner machine.
- Physical trust gates (USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY) remain BLOCKED until evidence from the real authorized Windows host. Mock/CI/session-only diagnose never signs them.
- Do not trust a process using PID, folder substring, HTTP 200, or name alone. Verify exact command-line argument tokens, process creation identity, full parent chain and listener; fail closed for ambiguity or missing metadata. Never kill `conhost`.
- Do not print, transmit, commit or package raw face images, embeddings, PnP device paths/serials, credentials, HMAC, cookies, SQLite or unrestricted logs. Evidence exports are redacted and hash-pinned.

## Completion contract
- Report actual tests with command, exit, environment and skips; never claim Windows/physical PASS from Linux CI or synthetic fixtures. Full-suite claims must include an exact run log.
- Require green GitHub checks and independent review before merging; CI is not replaced by an agent's self-reported PASS.
- Deliver four distinct bundles when source changes: FULL-SOURCE, CHANGED-SOURCE, WINDOWS-SAFE-EVIDENCE, COMPLETE-AUDIT. Include SHA256SUMS, manifest of relative paths, changelog, tests, known blockers and immutable Git commit. Never mislabel a packaging-freeze commit as remote PR tip.
- All Cursor development instructions/prompts must be written in English. Owner handoff may be Vietnamese. Attribution where applicable: `Phát triển bởi MyPC Việt Nam` -> `https://mypc.vn`.
