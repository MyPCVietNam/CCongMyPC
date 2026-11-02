# Acceptance matrix for next Cursor phase

Codes: `UNRUN` until real evidence; `PASS` only with exact test and source commit. Linux unit test is not Windows physical evidence.

| ID | Requirement / scenario | Observable acceptance evidence | Phase |
| --- | --- | --- | --- |
| A01 | Current source ancestry and clean tree | exact git HEAD, parent, diff manifest | SOURCE |
| A02 | SQLite + secrets backup | verified copies and test restore on disposable DataDir | SAFETY |
| A03 | Three Windows restarts | same DataDir; secret read and admin login on each | WIN-PHYSICAL |
| A04 | ACL idempotence | no change on healthy ACL | SECURITY |
| A05 | No secrets in logs | redacted logs, URL, argv, build artifacts | SECURITY |
| A06 | RBAC and CSRF | unauthorized CRUD and RTSP operations rejected | SECURITY |
| A07 | Camera URI SSRF | reject external/nonallowed target and rebinding | SECURITY |
| R01 | Single physical stream reader | one reader per unique physical stream despite 2 tabs | RUNTIME |
| R02 | Duplicate profiles distinct lifecycle | no inadvertent duplicate decoder on selection or list fetch | RUNTIME |
| R03 | H265 main stream TCP baseline | real measured stream, bitrate/codec/transport identified | WIN-PHYSICAL |
| R04 | TCP vs UDP controlled comparison | no claim without sequential data, no unsafe global change | WIN-PHYSICAL |
| R05 | H265 vs H264 sequential comparison | evidence codec supported, metrics by run | WIN-PHYSICAL |
| R06 | Wi-Fi vs RJ45 comparison | comparable same camera/same codec results where possible | WIN-PHYSICAL |
| R07 | HEVC missing reference | event counted with timestamp, no fake clean frame | RUNTIME |
| R08 | Recovery at clean keyframe | degraded -> fresh validated frame -> healthy, measured | RUNTIME |
| R09 | Bounded disconnect retry | exponential backoff + ceiling, no log flood | RUNTIME |
| R10 | Auth 401 error handling | final challenge outcome, not raw first 401 alone | RUNTIME |
| R11 | 404 endpoint error handling | stable no-respawn retry until configuration fixed | RUNTIME |
| R12 | Stop/archive process cleanup | handle/socket/worker released; no zombie decoder | RUNTIME |
| R13 | Multiple clients | bounded CPU/RAM, no more RTSP sessions | RUNTIME |
| R14 | Stale-frame guard | stalled timestamps -> STALE and blocked physical evidence | SAFETY |
| R15 | Source/provenance consistency | frame source camera ID, timestamp and immutable metadata | SAFETY |
| U01 | Smooth preview | actual measured browser update rate and latency | UI |
| U02 | Snapshot vs LIVE label | periodic still is labeled snapshot, not full-motion | UI |
| U03 | Browser hidden and selection switching | no overlapping stale response or leaked poller | UI |
| U04 | Browser reconnect/offline state | messages based on server truth; no sticky green LIVE | UI |
| U05 | Live performance isolation | preview lag does not degrade recognition capture pipeline | UI |
| C01 | Edit loads safe fields | name, host, RTSP path, username, mode, ROI match selected ID | CRUD |
| C02 | Credential keep | blank password never wipes existing credential | CRUD-SECURITY |
| C03 | Credential replacement | explicit action; no password in GET or logs | CRUD-SECURITY |
| C04 | Duplicate detection | accidental duplicate flagged, intentional profile supported | CRUD |
| C05 | Hard delete unreferenced | row and scoped credential removed transactionally | CRUD |
| C06 | Hard delete referenced | rejected with clear dependency counts, no cascades | CRUD |
| C07 | Archive referenced | hidden from active, evidence preserved, stream stopped | CRUD |
| C08 | Restore archived | same ID/history/credentials, reconnect only when requested | CRUD |
| C09 | Bulk preview | dry-run duplicate list and explicit owner confirmation | CRUD |
| C10 | #1 protected | deleting mock duplicates never touches #1 LIVE | CRUD |
| C11 | Foreign key and orphan check | no orphan secrets/regions/evidence after cleanup | CRUD-SECURITY |
| C12 | Mock disabled | 4xx actionable message, not HTTP 500 | CRUD |
| L01 | Correct Lab state transitions | UI and API enforce same state machine | LAB |
| L02 | LIVE distinct frame proof | measured fresh frames, unique timestamps, source pins | LAB |
| L03 | Browser challenge | valid after prerequisites, replay/skip rejected | LAB |
| L04 | Owner review | single operator accurately labeled; no skipped state | LAB |
| L05 | Evidence class vs gate | physical evidence class not equivalent to LAB_PASS | LAB |
| L06 | Error guidance | user sees unmet prerequisites and next permitted action | LAB |
| L07 | New run after failed sequence | old evidence preserved, new run can be completed | LAB |
| L08 | Mock/stale wrong-camera negative | never promoted as physical | LAB |
| L09 | Face Pilot separation | camera pass never auto-approves face identities | LAB |
| V01 | ROI coordinates | per-camera read/write and mapped native frame coordinates | VISION |
| V02 | Model weight verification | manifest SHA256, no hidden fixture fallback | VISION |
| V03 | H265 corruption and face enrollment | damaged frame not enrolled or marked valid | VISION |
| V04 | Owner physical pilot | consented known/unknown cases, measured results | BLOCKED until owner |
| P01 | npm advisories | each advisory classified and documented | DEPENDENCY |
| P02 | Windows PowerShell 5.1 | BOM scripts, no $HOME assignment, correct args | WINDOWS |
| P03 | Installer smoke | install/update/rollback and secrets preserved | BLOCKED until owner |
| D01 | Changed audit ZIP | ALL modified/added source, path manifest, SHA256, tests | DELIVERY |
| D02 | Full source ZIP | reproducible tree, secrets/venv/node_modules excluded | DELIVERY |
| D03 | Operator guide | Vietnamese exact same-DataDir recovery/upgrade steps | DELIVERY |

## Proposed physical measurements (not pre-approved corporate acceptance thresholds)
- At least 3 sequential stability runs, each targeting 30 minutes under clearly labeled conditions; owner can approve less comprehensive pilot observations but the gate remains BLOCKED if the specified evidence is incomplete.
- Record uninterrupted interval, count and maximum duration of black/corrupt frames, fresh-frame rate, sample-to-preview p50/p95 latency, timestamp age, RTSP reconnects, image resolution, CPU/RAM, codec, Wi-Fi or wired, and independent process count.
- Establish acceptance thresholds from observed baseline and attendance capture requirements before marking PASS; report unmet values honestly.
- Never manufacture evidence, backfill a missing frame as real, or infer genuine face recognition from camera-only diagnostics.
