# P02R Live Evidence

## Contract

PHYSICAL_VERIFIED for CAMERA_LAB / FACE_PILOT requires:

1. Server-issued lab run (`POST .../lab-runs`) with nonce + owner_challenge
2. Fresh LIVE measure (`.../measure`) — rejects MOCK/REPLAY/stale/disconnected
3. FACE_PILOT: ≥1 server `KNOWN:*` and ≥1 `UNKNOWN` case events
4. Owner one-time challenge review (`.../owner-review`)
5. Promote with fresh LIVE recheck (`.../promote-physical`) → evidence with `lab_run_id`
6. Separate HMAC-signed approval still required; gates remain false until signed + pins match

## Negative tests executed (Cloud)

| Case | Result |
|------|--------|
| EV01 client label counts → PHYSICAL | REJECT `NEED_LAB_RUN_PROMOTE` |
| EV05 MOCK measure | REJECT provenance |
| EV02 disconnected measure | REJECT |
| EV11 promote without owner review | REJECT `NEED_OWNER_REVIEW` |
| FACE_PILOT owner review without cases | REJECT `FACE_CASES_INSUFFICIENT` |
| ENV10 MOCK unlock CAMERA_LAB | gates remain false |

## Physical Windows LAN

**NOT_RUN / BLOCKED** — no EZVIZ company camera attached to this Cloud Agent.
