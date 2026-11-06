1. Verified LIVE requires non-ambiguous PnP hash + mapping_verified open target (index or video=name).
2. VID/PID or friendly-name alone is insufficient when duplicates exist.
3. Same USB stable_id + unchanged profile → preserve config_revision; material change rotates + revokes.
4. allow_ambiguous is diagnose/preview only — never trusted CAMERA_LIVE / HMAC.
5. RTSP trust lifecycle unchanged (no preferred_revision on RTSP fresh leases).
