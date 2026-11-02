# PR11 RealCam UX Harden — delivery handoff

Unified P0 security/integrity + RealCam reliability + npm + Operator-First UX.

- Baseline: `416bc2dcca4c6b117249aca02c5293a8e53ffeae` (`cursor/pr11-realcam-reliability-83a8`)
- Branch: `cursor/pr11-realcam-ux-harden-83a8`
- See `ACCEPTANCE_MATRIX.md`, `WINDOWS_UPGRADE_ACCEPTANCE_VI.md`, `NPM_ADVISORIES.md`, `AB_TEST_PLAN_VI.md`
- Screenshots under `screenshots/`
- Test reports under `reports/`
- ZIPs + SHA256 at packaging root of this folder

## ZIP notes

- **CHANGED** ZIP: files differing from baseline `416bc2d` plus this handoff.
- **FULL** ZIP: application source excluding `.venv`, `node_modules`, `release/*.zip`, and large `models/weights/*.onnx` (provision weights via `docs/MODEL_PROVISIONING.md`). Size kept under GitHub 100MB limit.
