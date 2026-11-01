# P02Q Source Custody

Date: 2026-11-02 (Asia/Ho_Chi_Minh)
Repo: https://github.com/MyPCVietNam/CCongMyPC

## Baseline (review facts — not reset permission)

| Item | Value |
|------|-------|
| Last reviewed PR #4 HEAD | `42c75d3f1e5052580d01bae410875f7ac8a26551` |
| PR #4 branch | `cursor/p015-hf-p02-camera-gateway-83a8` |
| `main` at review | LICENSE-only / not merged — **never used as code base** |
| Working branch | `cursor/p02hf-p02q-camera-quality-83a8` |
| Parent of first P02Q commit | `42c75d3f1e5052580d01bae410875f7ac8a26551` |
| P02Q implementation HEAD | `f3937a6287465a8bad9bccdb4cc4b48a17edddc4` |

## Custody actions

1. Fetched remotes; confirmed PR #4 HEAD still `42c75d3…` as code-bearing baseline.
2. Created feature branch from that HEAD (not from `main`).
3. Preserved uncommitted P02Q WIP already present on the branch and completed implementation.
4. No force-push. No merge to `main`.

## Diff summary (vs PR #4)

- LIVE path: `CameraSourceRegistry` + preview/configure/quality wired to same gateway.
- Strict `validate_live_rtsp_uri` (no userinfo/query/fragment; LAN-only; allowlisted ports).
- Immutable sealed BGR + `pixel_sha256` + `clone_pixels()`.
- Honest FPS / `overwritten_latest` / `DECODED_MEASURED` telemetry.
- Native YuNet inverse geometry; adaptive enhance shadow; paired A/B evaluator.
- Alembic `20261102_0004` quality/A-B tables (no biometric blobs).
- Vietnamese Camera quality UI + Windows lab script updates.
- Tests: +~33 new cases; full suite **118 passed** (see P02Q-TEST-REPORT.md).

## Status

- Working tree after commit: clean on feature branch.
- Physical CAMERA_LAB / FACE_PILOT / WINDOWS installer: **BLOCKED / NOT_RUN** (no company LAN evidence in this environment).
