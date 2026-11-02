"""Server-owned pilot / A/B evidence records — provenance classes fail-closed."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utc_time import utc_now
from app.models.entities import AbEvaluationRun, PilotEvidenceRecord

# Evidence trust ladder — only PHYSICAL_VERIFIED may back signed CAMERA_LAB / FACE_PILOT.
EVIDENCE_UNTRUSTED_IMPORT = "UNTRUSTED_IMPORT"
EVIDENCE_LIVE_PENDING = "LIVE_PENDING_REVIEW"
EVIDENCE_PHYSICAL = "PHYSICAL_VERIFIED"

KIND_CAMERA_LAB = "CAMERA_LAB"
KIND_FACE_PILOT = "FACE_PILOT"
KIND_AB_REVIEW = "AB_REVIEW"


@dataclass(frozen=True)
class EvidenceView:
    evidence_id: str
    kind: str
    evidence_class: str
    camera_id: int
    valid: bool
    code: str
    reason_vi: str


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


def require_physical_evidence(
    db: Session,
    *,
    kind: str,
    camera_id: int,
    evidence_id: str,
    pins: dict[str, str],
) -> EvidenceView:
    if not (evidence_id or "").strip():
        return EvidenceView(
            "",
            kind,
            "",
            camera_id,
            False,
            "EVIDENCE_ID_REQUIRED",
            "Thiếu evidence_id PHYSICAL_VERIFIED — không ký phê duyệt.",
        )
    row = db.scalar(
        select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == evidence_id)
    )
    if row is None or row.revoked:
        return EvidenceView(
            evidence_id,
            kind,
            "",
            camera_id,
            False,
            "EVIDENCE_NOT_FOUND",
            "Không tìm thấy bằng chứng hoặc đã thu hồi.",
        )
    if row.kind != kind or row.camera_id != camera_id:
        return EvidenceView(
            evidence_id,
            kind,
            row.evidence_class,
            camera_id,
            False,
            "EVIDENCE_MISMATCH",
            "Bằng chứng không khớp kind/camera.",
        )
    if row.evidence_class != EVIDENCE_PHYSICAL:
        return EvidenceView(
            evidence_id,
            kind,
            row.evidence_class,
            camera_id,
            False,
            "EVIDENCE_NOT_PHYSICAL",
            f"Hạng {row.evidence_class} không đủ — cần PHYSICAL_VERIFIED.",
        )
    if not (row.lab_run_id or "").strip():
        return EvidenceView(
            evidence_id,
            kind,
            row.evidence_class,
            camera_id,
            False,
            "EVIDENCE_MISSING_LAB_RUN",
            "PHYSICAL_VERIFIED thiếu lab_run_id — từ chối ký (cần FSM lab run).",
        )
    if (
        row.model_hash_pin != pins.get("model_hash_pin")
        or row.gallery_revision_pin != pins.get("gallery_revision_pin")
        or row.threshold_id_pin != pins.get("threshold_id_pin")
    ):
        return EvidenceView(
            evidence_id,
            kind,
            row.evidence_class,
            camera_id,
            False,
            "EVIDENCE_PIN_MISMATCH",
            "Pin model/gallery/threshold của bằng chứng không còn khớp server.",
        )
    return EvidenceView(
        row.evidence_id,
        row.kind,
        row.evidence_class,
        row.camera_id,
        True,
        "OK",
        "Bằng chứng PHYSICAL_VERIFIED còn hiệu lực.",
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
