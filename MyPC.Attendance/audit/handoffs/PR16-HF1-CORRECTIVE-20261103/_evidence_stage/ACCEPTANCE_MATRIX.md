# PR16-HF1 acceptance matrix

| Gate | Result |
|------|--------|
| CODE_FIX_PASS | PASS (323 pytest) |
| WINDOWS_TEST_PASS | OWNER |
| LIVE_STABILITY_PASS | BLOCKED |
| PHYSICAL_VERIFIED | OWNER prior (not re-proven) |
| CAMERA_LAB_SIGNED | BLOCKED |
| FACE_PILOT_PASS | BLOCKED |
| PRODUCTION_READY | HOLD — no main merge |

| Corrective | Result |
|------------|--------|
| Diag lanes survive Kiểm tra | CODE_FIX_PASS |
| UNKNOWN no clobber | CODE_FIX_PASS |
| FPS session reset | CODE_FIX_PASS |
| Evidence lookup | CODE_FIX_PASS |
| Secret UNKNOWN≠ORPHAN | CODE_FIX_PASS |
| Packaging custody | see COMPLETE-AUDIT |
