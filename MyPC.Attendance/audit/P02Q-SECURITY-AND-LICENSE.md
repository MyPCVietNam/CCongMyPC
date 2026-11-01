# P02Q Security & License

## Security controls added/hardened

- Single strict RTSP parser: no userinfo, query, fragment, percent-encoding tricks; RFC1918 / approved LAN hostnames; ports 554/8554/443/80.
- Credentials accepted only via protected body → encrypted secrets store; never returned in JSON.
- Diagnostic export: `camera_id` + `profile` + `uri=REDACTED` (no path/query).
- Preview/analyze/configure: authn + CSRF on writes + `CAMERA_MANAGE` where required.
- Immutable pixel buffers; revision isolation across rebind.
- ffprobe allowlist strips filename/url/auth-like keys.
- No unauthenticated video endpoints.

## Residual risks

- OpenCV/FFmpeg decode of untrusted RTSP still requires process isolation / resource limits on Windows host.
- DNS rebinding: hostname allowlist is policy-level; connect-time re-resolve enforcement needs owner LAN validation (HF08 partially UNIT, full OWNER_WINDOWS_LIVE BLOCKED).
- Person/exit detector weights still unlicensed for production — do not auto-close overtime.

## Privacy (VN PDPL context)

- No real face crops, embeddings, or visitor thumbnails in audit ZIP / public reports.
- A/B tables store aggregate metrics only.
- Workplace notice / lawful basis / retention remain owner+legal responsibilities before production.

## License notes

- YuNet MIT / SFace Apache-2.0 — pin hashes when weights present (unchanged from P01).
- FFmpeg: use system/OpenCV build; do not claim wrapper license covers LGPL/GPL features.
- YOLOX person weights: **not cleared** → exit automation BLOCKED.
