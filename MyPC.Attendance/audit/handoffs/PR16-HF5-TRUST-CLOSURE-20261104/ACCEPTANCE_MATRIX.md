# PR16-HF5 acceptance matrix

| Item | Result | Evidence |
|------|--------|----------|
| Baseline audit repros RED on unmodified HF4 | PASS | `BASELINE_FAIL.txt` |
| Same repros GREEN after fix (assertions preserved) | PASS | `TEST_REPORT.txt` |
| HTTP keep + nonempty password → secret changed, HMAC/PHYSICAL/lab revoked, rev rotated, binding stale | PASS | `test_pr16_hf5_credential_and_ab.py` |
| HTTP keep + username change (old password retained) → material invalidate | PASS | same |
| Explicit replace / remove material | PASS | same |
| Invalid `credential_action` → 422, no secret write | PASS | same |
| Blank password keep + name-only preserve trust | PASS | same |
| enabled false/true toggle without source change | PASS | same + HF4 suite |
| Host/path/model/firmware/MOCK material (HF4 regress) | PASS | `test_pr16_hf4_config_lifecycle.py` |
| Old signed approvals cannot reauth after material change | PASS | HF5 HTTP + unit |
| Rollback / outbox fail-closed preserved | PASS | prior HF suites + lifecycle |
| AUTO_VALIDATED missing AB → DENY | PASS | unit + integration |
| AUTO_VALIDATED REJECTED / non-promotable / severe blocker / pin or rev drift / wrong camera → DENY | PASS | integration |
| Valid AB + signed CAMERA_LAB + FACE_PILOT → allow | PASS | integration |
| pytest full (pinned 3.12 / FastAPI 0.115.14) | PASS | 398 passed |
| Frontend `npm ci` + typecheck + vitest + build; static sync | PASS | `FRONTEND_BUILD_REPORT.txt` (`index-BRx11ug4.js`) |
| Sensitive scan on COMPLETE nested ZIPs | PASS | packaging script fail-closed |
| Windows physical / soak / HEVC / owner HMAC sign / FACE_PILOT / INSTALLER / production | **BLOCKED** | owner-only; camera & PowerShell OFF in cloud |
