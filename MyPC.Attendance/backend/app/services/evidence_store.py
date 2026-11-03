"""Server-owned pilot / A/B evidence records — provenance classes fail-closed."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utc_time import to_utc_aware, utc_now
from app.models.entities import (
    AbEvaluationRun,
    CameraDevice,
    CameraLabRun,
    CameraLiveBinding,
    PilotEvidenceRecord,
)

# Evidence trust ladder — only PHYSICAL_VERIFIED may back signed CAMERA_LAB / FACE_PILOT.
EVIDENCE_UNTRUSTED_IMPORT = "UNTRUSTED_IMPORT"
EVIDENCE_LIVE_PENDING = "LIVE_PENDING_REVIEW"
EVIDENCE_PHYSICAL = "PHYSICAL_VERIFIED"

KIND_CAMERA_LAB = "CAMERA_LAB"
KIND_FACE_PILOT = "FACE_PILOT"
KIND_AB_REVIEW = "AB_REVIEW"

# Lab-run state required for signing (imported string to avoid circular import of constants)
LAB_STATE_PHYSICAL = "PHYSICAL_VERIFIED"


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: str
    kind: str
    evidence_class: str
    camera_id: int
    valid: bool
    code: str
    reason_vi: str


@dataclass(frozen=True)
class SignEligibility:
    """Authoritative CAMERA_LAB / FACE_PILOT signing gate — shared by list + POST + verify."""

    eligible: bool
    code: str
    reason_vi: str
    evidence_id: str = ""
    lab_run_id: str = ""
    config_revision: str = ""


def classify_client_ab_import(*, claimed_source_mix: str, sample_count: int) -> str:
    """Caller-supplied pairs are never physical evidence — even if labeled LIVE/REAL."""
    _ = claimed_source_mix, sample_count
    return EVIDENCE_UNTRUSTED_IMPORT


def record_untrusted_ab_import(
    db: Session,
    *,
    camera_id: int,
    run_id: str,
    source_mix: str,
    sample_count: int,
    metrics: dict[str, Any],
    blockers: list[str],
    operator: str,
    pins: dict[str, str],
    clock: datetime | None = None,
) -> AbEvaluationRun:
    now = clock or utc_now()
    # Fail closed: ignore client LIVE/REAL labels for trust class
    trust = classify_client_ab_import(claimed_source_mix=source_mix, sample_count=sample_count)
    row = AbEvaluationRun(
        camera_id=camera_id,
        run_id=run_id,
        source_mix=f"UNTRUSTED:{source_mix or 'EMPTY'}",
        sample_count=int(sample_count or 0),
        metrics_json=json.dumps(metrics, ensure_ascii=False),
        blockers_json=json.dumps(list(blockers) + ["UNTRUSTED_CLIENT_IMPORT"], ensure_ascii=False),
        can_auto_enable=False,
        approval_status="REJECTED",
        approved_by="",
        created_at=now,
        note_vi="Import client — UNTRUSTED_IMPORT; không thể AUTO_VALIDATED.",
        evidence_class=trust,
        config_revision="",
        model_hash_pin=pins.get("model_hash_pin") or "",
        gallery_revision_pin=pins.get("gallery_revision_pin") or "",
        threshold_id_pin=pins.get("threshold_id_pin") or "",
    )
    db.add(row)
    db.flush()
    return row


def create_evidence(
    db: Session,
    *,
    kind: str,
    evidence_class: str,
    camera_id: int,
    operator: str,
    pins: dict[str, str],
    config_revision: str = "",
    provenance: str = "",
    decoded_w: int | None = None,
    decoded_h: int | None = None,
    fps_measured: float | None = None,
    windows_host: str = "",
    labeled_known: int = 0,
    labeled_unknown: int = 0,
    frame_ids_json: str = "[]",
    note_vi: str = "",
    ab_run_id: str = "",
    lab_run_id: str = "",
    clock: datetime | None = None,
) -> PilotEvidenceRecord:
    if kind not in {KIND_CAMERA_LAB, KIND_FACE_PILOT, KIND_AB_REVIEW}:
        raise ValueError("Loại bằng chứng không hợp lệ.")
    if evidence_class not in {
        EVIDENCE_UNTRUSTED_IMPORT,
        EVIDENCE_LIVE_PENDING,
        EVIDENCE_PHYSICAL,
    }:
        raise ValueError("Hạng bằng chứng không hợp lệ.")
    if evidence_class == EVIDENCE_PHYSICAL:
        if not (lab_run_id or "").strip():
            raise ValueError(
                "PHYSICAL_VERIFIED cần lab_run_id server (CREATED→LIVE_MEASURED→OWNER_REVIEWED)."
            )
        if kind == KIND_CAMERA_LAB and not (
            provenance == "CAMERA_LIVE"
            and decoded_w
            and decoded_h
            and config_revision
            and pins.get("model_hash_pin")
        ):
            raise ValueError(
                "PHYSICAL_VERIFIED CAMERA_LAB cần CAMERA_LIVE + kích thước giải mã + config + pin."
            )
        if kind == KIND_FACE_PILOT and not (labeled_known > 0 and labeled_unknown > 0):
            raise ValueError(
                "PHYSICAL_VERIFIED FACE_PILOT cần mẫu labeled known và unknown (không lưu ảnh)."
            )
    now = clock or utc_now()
    eid = str(uuid.uuid4())
    meta = {
        "evidence_id": eid,
        "kind": kind,
        "evidence_class": evidence_class,
        "camera_id": camera_id,
        "lab_run_id": lab_run_id or "",
        "config_revision": config_revision,
        "provenance": provenance,
        "decoded_w": decoded_w,
        "decoded_h": decoded_h,
        "fps_measured": fps_measured,
        "windows_host": windows_host,
        "labeled_known": labeled_known,
        "labeled_unknown": labeled_unknown,
        "ab_run_id": ab_run_id,
        "pins": pins,
        # Never store face images / embeddings / RTSP secrets
    }
    row = PilotEvidenceRecord(
        evidence_id=eid,
        kind=kind,
        evidence_class=evidence_class,
        camera_id=camera_id,
        lab_run_id=lab_run_id or "",
        config_revision=config_revision or "",
        provenance=provenance or "",
        decoded_w=decoded_w,
        decoded_h=decoded_h,
        fps_measured=fps_measured,
        model_hash_pin=pins.get("model_hash_pin") or "",
        gallery_revision_pin=pins.get("gallery_revision_pin") or "",
        threshold_id_pin=pins.get("threshold_id_pin") or "",
        windows_host=windows_host or "",
        labeled_known=int(labeled_known or 0),
        labeled_unknown=int(labeled_unknown or 0),
        frame_ids_json=frame_ids_json or "[]",
        ab_run_id=ab_run_id or "",
        operator=operator,
        created_at=now,
        revoked=False,
        note_vi=note_vi,
        payload_json=json.dumps(meta, ensure_ascii=False, sort_keys=True),
    )
    db.add(row)
    db.flush()
    return row


def _current_camera_config_revision(db: Session, camera_id: int) -> tuple[str, str]:
    """Return (revision, error_code). Prefer CameraDevice; binding must agree if present."""
    cam = db.get(CameraDevice, camera_id)
    if cam is None:
        return "", "CAMERA_NOT_FOUND"
    if bool(getattr(cam, "archived", False)):
        return "", "CAMERA_ARCHIVED"
    rev = (cam.config_revision or "").strip()
    if not rev:
        return "", "CONFIG_REVISION_MISSING"
    binding = db.scalar(
        select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_id)
    )
    if binding is not None:
        brev = (binding.config_revision or "").strip()
        if brev and brev != rev:
            return "", "CONFIG_REVISION_BINDING_MISMATCH"
    return rev, ""


def evaluate_physical_sign_eligibility(
    db: Session,
    *,
    kind: str,
    camera_id: int,
    evidence_id: str,
    pins: dict[str, str] | None,
    clock: datetime | None = None,
) -> SignEligibility:
    """Single authoritative policy for UI listing and POST /quality/approvals.

    Fail closed. Never truncates config_revision for comparison.
    Performance: O(1) keyed lookups by evidence_id / lab run_id — safe for gate checks,
    not intended for per-frame biometric hot path.
    """
    now = to_utc_aware(clock) or utc_now()
    eid = (evidence_id or "").strip()
    if not eid:
        return SignEligibility(False, "EVIDENCE_ID_REQUIRED", "Thiếu evidence_id.")
    if kind not in {KIND_CAMERA_LAB, KIND_FACE_PILOT}:
        return SignEligibility(False, "KIND_INVALID", "Loại bằng chứng không ký được.")
    if pins is None or not (
        pins.get("model_hash_pin")
        and pins.get("gallery_revision_pin")
        and pins.get("threshold_id_pin")
    ):
        return SignEligibility(
            False,
            "PINS_UNAVAILABLE",
            "Thiếu pin server-derived — không đủ điều kiện ký.",
            evidence_id=eid,
        )

    row = db.scalar(select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == eid))
    if row is None:
        return SignEligibility(False, "EVIDENCE_NOT_FOUND", "Không tìm thấy bằng chứng.", evidence_id=eid)
    if row.revoked:
        return SignEligibility(
            False, "EVIDENCE_REVOKED", "Bằng chứng đã thu hồi.", evidence_id=eid
        )
    if row.kind != kind or int(row.camera_id) != int(camera_id):
        return SignEligibility(
            False,
            "EVIDENCE_MISMATCH",
            "Bằng chứng không khớp kind/camera.",
            evidence_id=eid,
        )
    if row.evidence_class != EVIDENCE_PHYSICAL:
        return SignEligibility(
            False,
            "EVIDENCE_NOT_PHYSICAL",
            f"Hạng {row.evidence_class} không đủ — cần PHYSICAL_VERIFIED.",
            evidence_id=eid,
        )

    current_rev, rev_err = _current_camera_config_revision(db, camera_id)
    if rev_err:
        return SignEligibility(False, rev_err, "Camera/config không đủ điều kiện ký.", evidence_id=eid)
    evid_rev = (row.config_revision or "").strip()
    if not evid_rev or evid_rev != current_rev:
        return SignEligibility(
            False,
            "CONFIG_REVISION_MISMATCH",
            "config_revision bằng chứng không khớp camera hiện tại (sau reconfigure).",
            evidence_id=eid,
            config_revision=evid_rev,
        )

    if (
        row.model_hash_pin != pins.get("model_hash_pin")
        or row.gallery_revision_pin != pins.get("gallery_revision_pin")
        or row.threshold_id_pin != pins.get("threshold_id_pin")
    ):
        return SignEligibility(
            False,
            "PIN_MISMATCH",
            "Pin model/gallery/threshold của bằng chứng không khớp server.",
            evidence_id=eid,
        )

    lab_id = (row.lab_run_id or "").strip()
    if not lab_id:
        return SignEligibility(
            False,
            "LAB_RUN_MISSING",
            "PHYSICAL_VERIFIED thiếu lab_run_id.",
            evidence_id=eid,
        )
    run = db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == lab_id))
    if run is None:
        return SignEligibility(
            False,
            "LAB_RUN_MISSING",
            "Không tìm thấy CameraLabRun tương ứng evidence.",
            evidence_id=eid,
            lab_run_id=lab_id,
        )
    if bool(run.revoked):
        return SignEligibility(
            False,
            "LAB_RUN_REVOKED",
            "Lab run đã thu hồi — không ký HMAC.",
            evidence_id=eid,
            lab_run_id=lab_id,
        )
    if (run.state or "") != LAB_STATE_PHYSICAL:
        return SignEligibility(
            False,
            "LAB_RUN_STATE_INVALID",
            f"Lab run state={run.state} — cần PHYSICAL_VERIFIED.",
            evidence_id=eid,
            lab_run_id=lab_id,
        )
    if int(run.camera_id) != int(camera_id) or (run.kind or "") != kind:
        return SignEligibility(
            False,
            "LAB_RUN_MISMATCH",
            "Lab run không khớp camera/kind.",
            evidence_id=eid,
            lab_run_id=lab_id,
        )
    run_rev = (run.config_revision or "").strip()
    if not run_rev or run_rev != current_rev or run_rev != evid_rev:
        return SignEligibility(
            False,
            "CONFIG_REVISION_MISMATCH",
            "Lab run config_revision không khớp evidence/camera hiện tại.",
            evidence_id=eid,
            lab_run_id=lab_id,
            config_revision=run_rev,
        )
    if run.expires_at is not None:
        exp = to_utc_aware(run.expires_at)
        if exp is not None and exp <= now:
            return SignEligibility(
                False,
                "LAB_RUN_EXPIRED",
                "Lab run đã hết hạn.",
                evidence_id=eid,
                lab_run_id=lab_id,
            )
    # When lab run carries pins, they must match server pins too
    if run.model_hash_pin or run.gallery_revision_pin or run.threshold_id_pin:
        if (
            run.model_hash_pin != pins.get("model_hash_pin")
            or run.gallery_revision_pin != pins.get("gallery_revision_pin")
            or run.threshold_id_pin != pins.get("threshold_id_pin")
        ):
            return SignEligibility(
                False,
                "PIN_MISMATCH",
                "Pin trên lab run không khớp server-derived.",
                evidence_id=eid,
                lab_run_id=lab_id,
            )
    if (run.provenance or "") and run.provenance != "CAMERA_LIVE" and kind == KIND_CAMERA_LAB:
        return SignEligibility(
            False,
            "LAB_RUN_PROVENANCE_INVALID",
            "Lab run provenance không phải CAMERA_LIVE.",
            evidence_id=eid,
            lab_run_id=lab_id,
        )

    return SignEligibility(
        True,
        "OK",
        "Evidence + lab run PHYSICAL_VERIFIED khớp config/pin hiện tại.",
        evidence_id=eid,
        lab_run_id=lab_id,
        config_revision=current_rev,
    )


def revoke_physical_evidence_for_camera(db: Session, *, camera_id: int, reason: str) -> int:
    """Mark prior PHYSICAL evidence non-signable after reconfigure — keep audit rows."""
    n = 0
    for row in db.scalars(
        select(PilotEvidenceRecord).where(
            PilotEvidenceRecord.camera_id == camera_id,
            PilotEvidenceRecord.revoked.is_(False),
            PilotEvidenceRecord.evidence_class == EVIDENCE_PHYSICAL,
        )
    ).all():
        row.revoked = True
        row.note_vi = (row.note_vi or "") + f" | REVOKED:{reason}"
        n += 1
    return n


def list_physical_evidence_for_camera(
    db: Session,
    *,
    camera_id: int,
    kind: str,
    pins: dict[str, str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Redacted PHYSICAL_VERIFIED rows — eligibility uses evaluate_physical_sign_eligibility."""
    q = (
        select(PilotEvidenceRecord)
        .where(
            PilotEvidenceRecord.camera_id == camera_id,
            PilotEvidenceRecord.kind == kind,
            PilotEvidenceRecord.evidence_class == EVIDENCE_PHYSICAL,
            PilotEvidenceRecord.revoked.is_(False),
        )
        .order_by(PilotEvidenceRecord.id.desc())
        .limit(max(1, min(int(limit), 50)))
    )
    out: list[dict[str, Any]] = []
    for row in db.scalars(q).all():
        elig = evaluate_physical_sign_eligibility(
            db,
            kind=kind,
            camera_id=camera_id,
            evidence_id=row.evidence_id,
            pins=pins,
        )
        out.append(
            {
                "evidence_id": row.evidence_id,
                "kind": row.kind,
                "evidence_class": row.evidence_class,
                "camera_id": row.camera_id,
                "lab_run_id": row.lab_run_id or "",
                # Display may truncate; comparisons never use this field
                "config_revision": row.config_revision or "",
                "config_revision_display": (row.config_revision or "")[:16],
                "provenance": row.provenance,
                "decoded_w": row.decoded_w,
                "decoded_h": row.decoded_h,
                "fps_measured": row.fps_measured,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "operator": row.operator or "",
                "pin_status": elig.code if elig.code in {"PIN_MISMATCH", "PINS_UNAVAILABLE"} else (
                    "PINS_MATCH" if elig.eligible else elig.code
                ),
                "eligible_for_sign": bool(elig.eligible),
                "eligible_reason": elig.code,
                "eligible_detail_vi": elig.reason_vi,
            }
        )
    return out


def require_physical_evidence(
    db: Session,
    *,
    kind: str,
    camera_id: int,
    evidence_id: str,
    pins: dict[str, str],
) -> EvidenceView:
    elig = evaluate_physical_sign_eligibility(
        db, kind=kind, camera_id=camera_id, evidence_id=evidence_id, pins=pins
    )
    row = db.scalar(
        select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == (evidence_id or ""))
    )
    evidence_class = row.evidence_class if row is not None else ""
    return EvidenceView(
        evidence_id or "",
        kind,
        evidence_class,
        camera_id,
        bool(elig.eligible),
        elig.code,
        elig.reason_vi,
    )


def ab_run_promotable(ab: AbEvaluationRun) -> tuple[bool, str]:
    """AUTO_VALIDATED only when AB is physically verified, reviewed, and can_auto_enable True."""
    if (ab.evidence_class or "") != EVIDENCE_PHYSICAL:
        return False, "AB_NOT_PHYSICAL"
    if (ab.approval_status or "").upper() != "APPROVED":
        return False, "AB_NOT_APPROVED"
    if not bool(ab.can_auto_enable):
        return False, "AB_CAN_AUTO_ENABLE_FALSE"
    blockers = []
    try:
        blockers = json.loads(ab.blockers_json or "[]")
    except json.JSONDecodeError:
        blockers = ["INVALID_BLOCKERS_JSON"]
    severe = {
        "HARD_REGRESSION_OR_FALSE_ACCEPT",
        "UNKNOWN_TO_KNOWN_ON_ENHANCE",
        "UNTRUSTED_CLIENT_IMPORT",
    }
    if severe.intersection(set(blockers)):
        return False, "AB_HAS_SEVERE_BLOCKER"
    if int(ab.sample_count or 0) <= 0:
        return False, "AB_EMPTY"
    return True, "OK"
