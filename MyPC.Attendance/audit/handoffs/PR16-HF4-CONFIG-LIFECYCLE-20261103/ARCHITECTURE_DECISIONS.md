# Architecture decisions (PR16-HF4)

## Material vs harmless PATCH
Material: host, rtsp_url_override, model, firmware, mock_mode transition, credential replace/remove.
Harmless: display name.
Material ⇒ new `config_revision`, revoke approvals+lab runs+PHYSICAL evidence (audit retained), unbind runtime, mark binding stale (`NEEDS_REBIND`).

## Temporary disable
`enabled=false` closes operational gate (`CAMERA_DISABLED`) without revoking PHYSICAL evidence so resume does not force re-lab. Signature rows may remain; `verify_active_approval` / eligibility fail closed while disabled.

## MOCK / archive
MOCK transition is material (revokes). Archived cameras fail `CAMERA_ARCHIVED`.

## Binding identity
Even if revisions match, binding host/path/port must not silently disagree with device RTSP identity (`SOURCE_IDENTITY_MISMATCH`).

## TTL layers
(a) Lab/challenge TTL — in-progress FSM only.
(b) PHYSICAL evidence — valid until revoke / material source change / pin drift.
(c) HMAC approval TTL — 30 days default; still cryptographically verified.
(d) Runtime LIVE health — separate decoder readiness.
(e) Config/source revision + binding freshness.

## AUTO_VALIDATED
Issuance still requires promotable AB + prior pilots; verification re-checks CAMERA_LAB and FACE_PILOT remain active.
