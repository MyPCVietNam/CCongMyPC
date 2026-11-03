"""Server-owned signed pilot / AUTO_VALIDATED approvals — evidence-backed, SQLite-safe HMAC."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_bootstrap import sign_approval_payload, verify_approval_signature
from app.core.utc_time import (
    AmbiguousTimestampError,
    canonical_utc_z,
    parse_canonical_utc_z,
    to_utc_aware,
    utc_now,
)
from app.models.entities import PilotApprovalRecord


@dataclass(frozen=True)
class ApprovalView:
    approval_id: str
    kind: str
    camera_id: int | None
    expires_at: datetime | None
    valid: bool
    reason_vi: str
    code: str = "OK"


def _canonical_dict(
    *,
    approval_id: str,
    kind: str,
    camera_id: int | None,
    model_hash_pin: str,
    gallery_revision_pin: str,
    threshold_id_pin: str,
    ab_run_id: str,
    evidence_id: str,
    expires_at: datetime | None,
    issued_by: str,
    issued_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "approval_id": approval_id,
        "kind": kind,
        "camera_id": camera_id,
        "model_hash_pin": model_hash_pin,
        "gallery_revision_pin": gallery_revision_pin,
        "threshold_id_pin": threshold_id_pin,
        "ab_run_id": ab_run_id,
        "evidence_id": evidence_id or "",
        "expires_at": canonical_utc_z(expires_at) if expires_at is not None else None,
        "issued_at": canonical_utc_z(issued_at) if issued_at is not None else None,
        "issued_by": issued_by,
        "v": 3,  # PR7: evidence_id + row/payload field integrity
    }


def _canonical_text(body: dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_matches_payload(row: PilotApprovalRecord, data: dict[str, Any]) -> bool:
    """HMAC proves payload integrity; also reject row↔payload drift (kind/id/issuer/pins/AB)."""
    try:
        if data.get("approval_id") != row.approval_id:
            return False
        if data.get("kind") != row.kind:
            return False
        if data.get("camera_id") != row.camera_id:
            return False
        if data.get("model_hash_pin") != (row.model_hash_pin or ""):
            return False
        if data.get("gallery_revision_pin") != (row.gallery_revision_pin or ""):
            return False
        if data.get("threshold_id_pin") != (row.threshold_id_pin or ""):
            return False
        if data.get("ab_run_id", "") != (row.ab_run_id or ""):
            return False
        if data.get("evidence_id", "") != (getattr(row, "evidence_id", None) or ""):
            return False
        if data.get("issued_by") != (row.issued_by or ""):
            return False
        # Expiry: signed canonical must match row when both present
        signed_exp = data.get("expires_at")
        if row.expires_at is not None:
            row_exp_z = canonical_utc_z(to_utc_aware(row.expires_at))  # type: ignore[arg-type]
            if signed_exp != row_exp_z:
                return False
        elif signed_exp not in (None, ""):
            return False
        return True
    except AmbiguousTimestampError:
        return False


def issue_approval(
    db: Session,
    *,
    secret_key: str,
    kind: str,
    camera_id: int | None,
    issued_by: str,
    model_hash_pin: str,
    gallery_revision_pin: str,
    threshold_id_pin: str,
    ab_run_id: str = "",
    evidence_id: str = "",
    ttl_hours: int = 24 * 30,
    note_vi: str = "",
    clock: datetime | None = None,
) -> PilotApprovalRecord:
    if kind not in {"CAMERA_LAB", "FACE_PILOT", "AUTO_VALIDATED"}:
        raise ValueError("Loại phê duyệt không hợp lệ")
    if not (model_hash_pin and gallery_revision_pin and threshold_id_pin):
        raise ValueError("Thiếu hash pin model/gallery/threshold (server-derived).")
    if kind == "AUTO_VALIDATED" and not (ab_run_id or "").strip():
        raise ValueError("AUTO_VALIDATED yêu cầu ab_run_id từ chạy A/B server.")
    if camera_id is None and kind in {"CAMERA_LAB", "FACE_PILOT", "AUTO_VALIDATED"}:
        raise ValueError("Phê duyệt phải gắn camera_id cụ thể.")
    if kind in {"CAMERA_LAB", "FACE_PILOT"} and not (evidence_id or "").strip():
        raise ValueError("CAMERA_LAB/FACE_PILOT yêu cầu evidence_id PHYSICAL_VERIFIED.")
    import uuid

    now = clock or utc_now()
    now = to_utc_aware(now) or utc_now()
    expires = now + timedelta(hours=ttl_hours)
    approval_id = str(uuid.uuid4())
    body = _canonical_dict(
        approval_id=approval_id,
        kind=kind,
        camera_id=camera_id,
        model_hash_pin=model_hash_pin,
        gallery_revision_pin=gallery_revision_pin,
        threshold_id_pin=threshold_id_pin,
        ab_run_id=ab_run_id or "",
        evidence_id=evidence_id or "",
        expires_at=expires,
        issued_by=issued_by,
        issued_at=now,
    )
    payload = _canonical_text(body)
    signature = sign_approval_payload(secret_key, payload)
    row = PilotApprovalRecord(
        approval_id=approval_id,
        kind=kind,
        camera_id=camera_id,
        model_hash_pin=model_hash_pin,
        gallery_revision_pin=gallery_revision_pin,
        threshold_id_pin=threshold_id_pin,
        ab_run_id=ab_run_id or "",
        evidence_id=evidence_id or "",
        issued_by=issued_by,
        issued_at=now,
        expires_at=expires,
        signature=signature,
        revoked=False,
        note_vi=note_vi,
        payload_json=payload,
    )
    db.add(row)
    db.flush()
    return row


def verify_active_approval(
    db: Session,
    *,
    secret_key: str,
    kind: str,
    camera_id: int | None = None,
    model_hash_pin: str | None = None,
    gallery_revision_pin: str | None = None,
    threshold_id_pin: str | None = None,
    require_pins: bool = True,
    require_camera_id: bool = True,
    clock: datetime | None = None,
) -> ApprovalView | None:
    """
    Fail closed: missing pins/camera when required → DENIED (not skip).
    HMAC verified against stored payload_json; row fields must match payload.

    For CAMERA_LAB / FACE_PILOT: after HMAC+expiry+pin checks, re-validate backing
    PHYSICAL evidence via evaluate_physical_sign_eligibility (live relational gate).
    Invalid/revoked/stale evidence or lab run ⇒ approval does not authorize the gate.
    AUTO_VALIDATED (PR16-HF4): after HMAC checks, require both CAMERA_LAB and FACE_PILOT
    still verify_active under the same pins/camera (dependency lifecycle). Cost: O(1)
    keyed SQLite lookups per candidate — not a per-frame biometric hot path.
    """
    now = to_utc_aware(clock) or utc_now()
    if require_camera_id and camera_id is None:
        return ApprovalView(
            "", kind, None, None, False, "Thiếu camera_id khi xác minh phê duyệt.", "DENIED_NO_CAMERA"
        )
    if require_pins and not (model_hash_pin and gallery_revision_pin and threshold_id_pin):
        return ApprovalView(
            "",
            kind,
            camera_id,
            None,
            False,
            "Thiếu pin model/gallery/threshold — từ chối (fail-closed).",
            "DENIED_MISSING_PINS",
        )

    q = select(PilotApprovalRecord).where(
        PilotApprovalRecord.kind == kind,
        PilotApprovalRecord.revoked.is_(False),
    )
    if camera_id is not None:
        q = q.where(PilotApprovalRecord.camera_id == camera_id)
    rows = list(db.scalars(q.order_by(PilotApprovalRecord.id.desc())).all())
    need_evidence_gate = kind in {"CAMERA_LAB", "FACE_PILOT"}
    need_pilot_deps = kind == "AUTO_VALIDATED"
    for row in rows:
        payload = row.payload_json or ""
        if not payload or not verify_approval_signature(secret_key, payload, row.signature or ""):
            continue
        try:
            data = json.loads(payload)
            exp = parse_canonical_utc_z(data.get("expires_at"))
        except (json.JSONDecodeError, AmbiguousTimestampError, TypeError):
            continue
        if not _row_matches_payload(row, data):
            continue
        if data.get("kind") != kind:
            continue
        if exp is not None and exp <= now:
            continue
        if model_hash_pin and data.get("model_hash_pin") != model_hash_pin:
            continue
        if gallery_revision_pin and data.get("gallery_revision_pin") != gallery_revision_pin:
            continue
        if threshold_id_pin and data.get("threshold_id_pin") != threshold_id_pin:
            continue
        if camera_id is not None and data.get("camera_id") != camera_id:
            continue
        if need_evidence_gate:
            eid = (data.get("evidence_id") or getattr(row, "evidence_id", None) or "").strip()
            if not eid or camera_id is None:
                continue
            from app.services.evidence_store import evaluate_physical_sign_eligibility

            elig = evaluate_physical_sign_eligibility(
                db,
                kind=kind,
                camera_id=int(camera_id),
                evidence_id=eid,
                pins={
                    "model_hash_pin": model_hash_pin or "",
                    "gallery_revision_pin": gallery_revision_pin or "",
                    "threshold_id_pin": threshold_id_pin or "",
                },
                clock=now,
            )
            if not elig.eligible:
                # Live relational invalidation — do not authorize; keep signature row intact
                continue
        if need_pilot_deps:
            if camera_id is None:
                continue
            deps_ok = True
            for dep_kind in ("CAMERA_LAB", "FACE_PILOT"):
                dep = verify_active_approval(
                    db,
                    secret_key=secret_key,
                    kind=dep_kind,
                    camera_id=camera_id,
                    model_hash_pin=model_hash_pin,
                    gallery_revision_pin=gallery_revision_pin,
                    threshold_id_pin=threshold_id_pin,
                    require_pins=True,
                    require_camera_id=True,
                    clock=now,
                )
                if dep is None or not dep.valid:
                    deps_ok = False
                    break
            if not deps_ok:
                continue
        return ApprovalView(
            approval_id=row.approval_id,
            kind=row.kind,
            camera_id=row.camera_id,
            expires_at=exp,
            valid=True,
            reason_vi="Phê duyệt server còn hiệu lực (HMAC + UTC Zulu + khớp hàng DB + evidence).",
            code="OK",
        )
    return None


def revoke_approvals(
    db: Session, *, kind: str | None = None, camera_id: int | None = None, reason: str = ""
) -> int:
    q = select(PilotApprovalRecord).where(PilotApprovalRecord.revoked.is_(False))
    if kind:
        q = q.where(PilotApprovalRecord.kind == kind)
    if camera_id is not None:
        q = q.where(PilotApprovalRecord.camera_id == camera_id)
    n = 0
    for row in db.scalars(q).all():
        row.revoked = True
        row.note_vi = (row.note_vi or "") + f" | REVOKED:{reason}"
        n += 1
    return n


def derive_server_pins(
    *,
    model_hash: str,
    gallery_revision: str,
    threshold_id: str,
) -> dict[str, str]:
    if not (model_hash and gallery_revision and threshold_id):
        raise ValueError("Không suy ra được pin server (thiếu model/gallery/threshold).")
    return {
        "model_hash_pin": model_hash,
        "gallery_revision_pin": gallery_revision,
        "threshold_id_pin": threshold_id,
    }
