"""Server-owned signed pilot / AUTO_VALIDATED approvals — never JSON-only claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_bootstrap import sign_approval_payload, verify_approval_signature
from app.models.entities import PilotApprovalRecord


@dataclass(frozen=True)
class ApprovalView:
    approval_id: str
    kind: str
    camera_id: int | None
    expires_at: datetime | None
    valid: bool
    reason_vi: str


def _canonical_payload(row: PilotApprovalRecord) -> str:
    body = {
        "approval_id": row.approval_id,
        "kind": row.kind,
        "camera_id": row.camera_id,
        "model_hash_pin": row.model_hash_pin,
        "gallery_revision_pin": row.gallery_revision_pin,
        "threshold_id_pin": row.threshold_id_pin,
        "ab_run_id": row.ab_run_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "issued_by": row.issued_by,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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
    ttl_hours: int = 24 * 30,
    note_vi: str = "",
) -> PilotApprovalRecord:
    if kind not in {"CAMERA_LAB", "FACE_PILOT", "AUTO_VALIDATED"}:
        raise ValueError("Loại phê duyệt không hợp lệ")
    if not (model_hash_pin and gallery_revision_pin and threshold_id_pin):
        raise ValueError("Thiếu hash pin model/gallery/threshold")
    import uuid

    now = datetime.now(timezone.utc)
    row = PilotApprovalRecord(
        approval_id=str(uuid.uuid4()),
        kind=kind,
        camera_id=camera_id,
        model_hash_pin=model_hash_pin,
        gallery_revision_pin=gallery_revision_pin,
        threshold_id_pin=threshold_id_pin,
        ab_run_id=ab_run_id or "",
        issued_by=issued_by,
        issued_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        signature="",
        revoked=False,
        note_vi=note_vi,
        payload_json="{}",
    )
    row.signature = sign_approval_payload(secret_key, _canonical_payload(row))
    row.payload_json = _canonical_payload(row)
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
) -> ApprovalView | None:
    now = datetime.now(timezone.utc)
    q = select(PilotApprovalRecord).where(
        PilotApprovalRecord.kind == kind,
        PilotApprovalRecord.revoked.is_(False),
    )
    if camera_id is not None:
        q = q.where(PilotApprovalRecord.camera_id == camera_id)
    rows = list(db.scalars(q.order_by(PilotApprovalRecord.id.desc())).all())
    for row in rows:
        if row.expires_at and row.expires_at < now:
            continue
        if model_hash_pin and row.model_hash_pin != model_hash_pin:
            continue
        if gallery_revision_pin and row.gallery_revision_pin != gallery_revision_pin:
            continue
        if threshold_id_pin and row.threshold_id_pin != threshold_id_pin:
            continue
        payload = _canonical_payload(row)
        if not verify_approval_signature(secret_key, payload, row.signature):
            continue
        return ApprovalView(
            approval_id=row.approval_id,
            kind=row.kind,
            camera_id=row.camera_id,
            expires_at=row.expires_at,
            valid=True,
            reason_vi="Phê duyệt server còn hiệu lực.",
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
