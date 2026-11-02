# PR7 Corrective — Security

- HMAC proves server issuance of payload; PHYSICAL_VERIFIED evidence proves lab claims separately.
- Client LIVE/REAL labels on AB imports ignored (trust class UNTRUSTED_IMPORT).
- Fail closed on pin mismatch, row↔payload drift, missing evidence, `can_auto_enable=False`.
- RTSP IPv4 pin + secret redaction preserved.
- No face images / embeddings / RTSP passwords in audits or ZIPs.
- Shadow observe never writes authoritative attendance.
