# P02-USB-HF1 changelog

- Link WMI/PnP hashed identity to DirectShow open target (index and/or `video=FriendlyName`).
- Fail closed on name collisions / ambiguous index-only; `allow_ambiguous` never grants trusted LIVE.
- Preserve `config_revision` on non-material same-USB rebind (registry preferred_revision).
- CameraPage shows mapping_verified / trusted_live_eligible.
- Owner candidate script Prepare/Preflight/Start/Export for 18878.
- Owner repro tests converted RED→GREEN; index-only remains expected 409.
