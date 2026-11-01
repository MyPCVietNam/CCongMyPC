# Documented assumptions (P00)

1. Default listen address `127.0.0.1:8765`; LAN bind is opt-in.
2. First-run bootstrap creates a SYSTEM_ADMIN via interactive setup; no default password in source. Dev/test uses env `MYPC_BOOTSTRAP_PASSWORD` only when set.
3. Mock Camera is the default until a camera device is configured and diagnostics pass.
4. EXIT_VERIFICATION_GATE starts as `BLOCKED` until real overhead-camera calibration proves direction/identity association.
5. PDF export deferred until a redistributable Unicode Vietnamese font is audited into the package.
6. go2rtc Windows binary download/packaging deferred to P06; P00 ships config template + mock gateway.
7. OpenCV YuNet/SFace model files are listed in `models/manifest.json`; download scripts fetch only after license/hash verification — not bundled with real employee faces.
8. Timezone default `Asia/Ho_Chi_Minh`; no DST in Vietnam.
9. Single-writer SQLite with busy_timeout=5000 and WAL.
10. Session auth via signed HttpOnly cookie; CSRF double-submit for cookie writes.
