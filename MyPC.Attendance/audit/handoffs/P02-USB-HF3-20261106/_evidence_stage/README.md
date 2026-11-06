# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: COM **exactly-once** release + PS 5.1 Update leaf rename/rollback,
preserving IPropertyBag stage telemetry and strict DevicePath identity matching.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `ff6789e`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` HF3 DataDir only. Use `-Mode Update` on an already-prepared candidate — do **not** re-run Prepare.

## Pins (filled after packaging freeze commit)

Pre-fix tip: `ff6789ecd15ede618101e6a4c4938c3290ed1748`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

Property-bag prior tip: `05f6ba991b4b43b3719125551298b18441578bcb`

See `SHA256SUMS-COMPLETE.txt` / packaging freeze commit after agent push for immutable raw URL.
