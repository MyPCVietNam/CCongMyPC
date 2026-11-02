# PR11-HF Changelog

- Alembic `20261102_0010`: camera `archived`, `username_hint`, `connection_status`, `config_revision`.
- Camera GET/PATCH/archive/restore/DELETE + credential policy service.
- Fixed LIVE configure blank-password secret wipe; returns CONFIG_SAVED not LIVE verified.
- RTSP staged probe endpoint; bounded gateway reconnect; stop LIVE per camera.
- CameraPage Vietnamese CRUD UI with password-keep UX and poll backoff.
- Tests + audits + release ZIPs.
