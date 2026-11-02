# PR11-HF Security

- Camera writes require `CAMERA_MANAGE` + CSRF; pending password-change gate unchanged.
- Passwords never returned by API; blank password = keep; replace is explicit.
- RTSP URI stored/edited without userinfo; capture URI with secrets stays in-process only.
- SecretsStore: delete only `camera-*.bin`; master.key protected; Windows ACL best-effort.
- Hard delete denied when observations/lab/approvals/AB history exist.
- Probe/auth attempts bounded (single DESCRIBE with auth); no brute-force paths/passwords.
- Audits redact secrets.
