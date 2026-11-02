"""Server-issued CAMERA_LAB / FACE_PILOT runs with freshness + owner review state machine."""

from __future__ import annotations

import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utc_time import utc_now
from app.models.entities import CameraLabRun, FacePilotCaseEvent, PilotEvidenceRecord
from app.services.evidence_store import EVIDENCE_PHYSICAL, create_evidence
from app.vision.faces.types import MatchOutcome

STATE_CREATED = "CREATED"
STATE_LIVE_MEASURED = "LIVE_MEASURED"
STATE_OWNER_REVIEWED = "OWNER_REVIEWED"
STATE_PHYSICAL = "PHYSICAL_VERIFIED"
STATE_REJECTED = "REJECTED"

MAX_FRAME_AGE_S = 3.0
RUN_TTL_HOURS = 8


class LabRunError(ValueError):
    def __init__(self, code: str, message_vi: str) -> None:
        super().__init__(message_vi)
        self.code = code
        self.message_vi = message_vi


def start_lab_run(
    db: Session,
    *,
    camera_id: int,
    kind: str,
    operator: str,
    pins: dict[str, str],
    profile: str = "MAIN",
    clock: datetime | None = None,
) -> CameraLabRun:
    if kind not in {"CAMERA_LAB", "FACE_PILOT"}:
        raise LabRunError("KIND_INVALID", "Loại lab run không hợp lệ.")
    now = clock or utc_now()
    run = CameraLabRun(
        run_id=str(uuid.uuid4()),
        nonce=secrets.token_urlsafe(24),
        kind=kind,
        camera_id=camera_id,
        state=STATE_CREATED,
        profile=profile or "MAIN",
        model_hash_pin=pins.get("model_hash_pin") or "",
        gallery_revision_pin=pins.get("gallery_revision_pin") or "",
        threshold_id_pin=pins.get("threshold_id_pin") or "",
        operator=operator,
        started_at=now,
        expires_at=now + timedelta(hours=RUN_TTL_HOURS),
        owner_challenge=secrets.token_urlsafe(16),
        note_vi="Lab run server — chờ đo LIVE tươi.",
    )
    db.add(run)
    db.flush()
    return run


def _require_run(db: Session, run_id: str, camera_id: int) -> CameraLabRun:
    row = db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == run_id))
    if row is None or row.camera_id != camera_id:
        raise LabRunError("LAB_RUN_NOT_FOUND", "Không tìm thấy lab run cho camera này.")
    if row.revoked:
        raise LabRunError("LAB_RUN_REVOKED", "Lab run đã thu hồi.")
    now = utc_now()
    if row.expires_at is not None and row.expires_at <= now:
        row.state = STATE_REJECTED
        raise LabRunError("LAB_RUN_EXPIRED", "Lab run đã hết hạn.")
    return row


def measure_live_frames(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    registry: Any,
    samples: int = 5,
) -> CameraLabRun:
    """Capture fresh CAMERA_LIVE frames NOW — reject MOCK/stale/health-only W/H."""
    run = _require_run(db, run_id, camera_id)
    if run.state not in {STATE_CREATED, STATE_LIVE_MEASURED}:
        raise LabRunError("LAB_STATE", f"Không đo được ở trạng thái {run.state}.")
    if registry is None:
        raise LabRunError("REGISTRY_MISSING", "Registry camera chưa sẵn sàng.")
    bound = registry.get(camera_id)
    if bound is None:
        raise LabRunError("LIVE_NOT_BOUND", "Camera chưa gắn nguồn LIVE.")
    if bound.provenance.value != "CAMERA_LIVE":
        raise LabRunError("PROVENANCE_NOT_LIVE", "MOCK/REPLAY không đủ PHYSICAL_VERIFIED.")

    frame_ids: list[str] = []
    widths: list[int] = []
    heights: list[int] = []
    ages: list[float] = []
    recv_times: list[float] = []
    for _ in range(max(3, min(samples, 15))):
        try:
            bound2, fr = registry.get_frame(
                camera_id,
                require_live=True,
                for_biometric=True,
                allow_stale=False,
                max_age_s=MAX_FRAME_AGE_S,
            )
        except Exception as exc:  # FrameAccessError
            code = getattr(exc, "code", "FRAME_ACCESS")
            raise LabRunError(str(code), getattr(exc, "message_vi", str(exc))) from exc
        if bound2.config_revision != bound.config_revision:
            raise LabRunError("CONFIG_CHANGED_MID_MEASURE", "Config đổi giữa lúc đo.")
        age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
        if age > MAX_FRAME_AGE_S:
            raise LabRunError("FRAME_TOO_OLD", f"Khung hình già {age:.2f}s.")
        if fr.width <= 0 or fr.height <= 0:
            raise LabRunError("EMPTY_FRAME", "Khung hình không có kích thước giải mã.")
        frame_ids.append(fr.frame_id)
        widths.append(int(fr.width))
        heights.append(int(fr.height))
        ages.append(age * 1000.0)
        recv_times.append(fr.receive_monotonic or time.monotonic())
        time.sleep(0.05)

    # Monotonic receive times
    for a, b in zip(recv_times, recv_times[1:]):
        if b + 1e-9 < a:
            raise LabRunError("NONMONOTONIC_RECV", "Thời gian nhận khung không đơn điệu.")

    fps = 0.0
    if len(recv_times) >= 2 and (recv_times[-1] - recv_times[0]) > 0:
        fps = (len(recv_times) - 1) / (recv_times[-1] - recv_times[0])

    # Prefer actual frame dims — never client claims
    w = widths[-1]
    h = heights[-1]
    if any(x != w for x in widths) or any(x != h for x in heights):
        # allow minor variance only if same — otherwise reject
        raise LabRunError("UNSTABLE_DIMENSIONS", "Kích thước giải mã không ổn định trong cửa sổ đo.")

    health = bound.gateway.health()
    # Stale health W/H after disconnect must not satisfy if frames failed — frames already OK
    run.state = STATE_LIVE_MEASURED
    run.config_revision = bound.config_revision
    run.provenance = bound.provenance.value
    run.source_generation = bound.config_revision  # generation pin
    run.profile = bound.profile or run.profile
    run.decoded_w = w
    run.decoded_h = h
    run.fps_measured = float(fps)
    run.frame_age_ms = float(ages[-1])
    run.frame_ids_json = json.dumps(frame_ids)
    run.reconnect_count = int(getattr(health, "reconnect_count", 0) or 0)
    run.decode_errors = int(getattr(health, "decode_errors", 0) or 0)
    run.measured_at = utc_now()
    run.metrics_json = json.dumps(
        {
            "samples": len(frame_ids),
            "decoded_w": w,
            "decoded_h": h,
            "fps_measured": fps,
            "frame_age_ms_last": ages[-1],
            "note": "SERVER_MEASURED_LIVE",
        },
        ensure_ascii=False,
    )
    run.note_vi = "Đã đo LIVE tươi trên server — chờ owner review."
    db.flush()
    return run


def record_face_pilot_case(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    registry: Any,
    pipeline: Any,
    gallery_pairs: list,
    pins: dict[str, str],
    truth_label: str,
    condition: str = "DAY",
) -> FacePilotCaseEvent:
    """Pull LIVE frame NOW and evaluate — client counts alone are insufficient."""
    run = _require_run(db, run_id, camera_id)
    if run.kind != "FACE_PILOT":
        raise LabRunError("NOT_FACE_PILOT_RUN", "Lab run không phải FACE_PILOT.")
    if run.state not in {STATE_LIVE_MEASURED, STATE_OWNER_REVIEWED}:
        raise LabRunError("NEED_LIVE_MEASURED", "Cần đo LIVE trước khi ghi case FACE_PILOT.")
    if not gallery_pairs and not str(truth_label).upper().startswith("UNKNOWN"):
        # known truth requires gallery; unknown can still run empty→UNKNOWN
        pass
    try:
        bound, fr = registry.get_frame(
            camera_id,
            require_live=True,
            for_biometric=True,
            allow_stale=False,
            max_age_s=MAX_FRAME_AGE_S,
        )
    except Exception as exc:
        raise LabRunError(
            getattr(exc, "code", "FRAME_ACCESS"),
            getattr(exc, "message_vi", str(exc)),
        ) from exc
    if bound.config_revision != run.config_revision:
        raise LabRunError("CONFIG_REVISION_CHANGED", "Config đổi sau khi đo — từ chối case.")
    if fr.width != run.decoded_w or fr.height != run.decoded_h:
        raise LabRunError("DIM_MISMATCH", "Kích thước khung không khớp lab run đã đo.")

    truth = (truth_label or "").strip().upper()
    if not (truth == "UNKNOWN" or truth.startswith("KNOWN:")):
        raise LabRunError("TRUTH_INVALID", "truth_label phải UNKNOWN hoặc KNOWN:<employee_id>.")

    t0 = time.perf_counter()
    result = pipeline.verify(fr.clone_pixels(), gallery=gallery_pairs)
    latency = (time.perf_counter() - t0) * 1000.0
    if result.outcome == MatchOutcome.MATCH and result.employee_id is not None:
        pred = f"KNOWN:{result.employee_id}"
    elif result.outcome == MatchOutcome.UNKNOWN:
        pred = "UNKNOWN"
    elif result.outcome == MatchOutcome.AMBIGUOUS:
        pred = "AMBIGUOUS"
    elif result.outcome == MatchOutcome.NO_FACE:
        pred = "NO_FACE"
    else:
        pred = result.outcome.value

    outcome = "AMBIGUOUS"
    if truth == "UNKNOWN":
        if pred == "UNKNOWN":
            outcome = "CORRECT"
        elif pred.startswith("KNOWN:"):
            outcome = "FALSE_ACCEPT"
        elif pred == "NO_FACE":
            outcome = "MISS"
        else:
            outcome = "AMBIGUOUS"
    else:
        if pred == truth:
            outcome = "CORRECT"
        elif pred.startswith("KNOWN:") and pred != truth:
            outcome = "WRONG"
        elif pred == "UNKNOWN":
            outcome = "MISS"
        elif pred == "NO_FACE":
            outcome = "MISS"
        else:
            outcome = "AMBIGUOUS"

    q = result.quality
    case = FacePilotCaseEvent(
        case_id=str(uuid.uuid4()),
        lab_run_id=run.run_id,
        camera_id=camera_id,
        frame_id=fr.frame_id,
        config_revision=run.config_revision,
        truth_label=truth,
        pred_label=pred,
        outcome=outcome,
        similarity=result.similarity,
        condition=(condition or "DAY").upper(),
        native_face_width_px=int(q.face_width_px) if q and q.face_width_px else None,
        latency_ms=round(latency, 3),
        model_hash_pin=pins.get("model_hash_pin") or run.model_hash_pin,
        gallery_revision_pin=pins.get("gallery_revision_pin") or run.gallery_revision_pin,
        threshold_id_pin=pins.get("threshold_id_pin") or run.threshold_id_pin,
        created_at=utc_now(),
        note_vi="Case server-generated — không lưu ảnh/embedding.",
    )
    db.add(case)
    db.flush()
    return case


def owner_review(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    operator: str,
    challenge: str,
) -> CameraLabRun:
    run = _require_run(db, run_id, camera_id)
    if run.state != STATE_LIVE_MEASURED:
        raise LabRunError("NEED_LIVE_MEASURED", "Owner review cần trạng thái LIVE_MEASURED.")
    if not challenge or not secrets.compare_digest(challenge, run.owner_challenge or ""):
        raise LabRunError("CHALLENGE_INVALID", "Challenge owner không khớp — chống replay.")
    if run.kind == "FACE_PILOT":
        known_n = db.scalar(
            select(func.count())
            .select_from(FacePilotCaseEvent)
            .where(
                FacePilotCaseEvent.lab_run_id == run.run_id,
                FacePilotCaseEvent.truth_label.like("KNOWN:%"),
            )
        )
        unk_n = db.scalar(
            select(func.count())
            .select_from(FacePilotCaseEvent)
            .where(
                FacePilotCaseEvent.lab_run_id == run.run_id,
                FacePilotCaseEvent.truth_label == "UNKNOWN",
            )
        )
        if int(known_n or 0) < 1 or int(unk_n or 0) < 1:
            raise LabRunError(
                "FACE_CASES_INSUFFICIENT",
                "FACE_PILOT cần ≥1 case KNOWN và ≥1 case UNKNOWN do server đo.",
            )
    run.state = STATE_OWNER_REVIEWED
    run.owner_reviewed_by = operator
    run.owner_reviewed_at = utc_now()
    # rotate challenge after use (one-time)
    run.owner_challenge = secrets.token_urlsafe(16)
    run.note_vi = "Owner đã review — có thể promote PHYSICAL_VERIFIED."
    db.flush()
    return run


def promote_physical(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    operator: str,
    registry: Any,
    pins: dict[str, str],
) -> PilotEvidenceRecord:
    """PHYSICAL_VERIFIED only after LIVE_MEASURED + OWNER_REVIEWED + fresh recheck."""
    run = _require_run(db, run_id, camera_id)
    if run.state != STATE_OWNER_REVIEWED:
        raise LabRunError(
            "NEED_OWNER_REVIEW",
            "Không PHYSICAL_VERIFIED khi chưa OWNER_REVIEWED (EV11).",
        )
    # Pin match
    if (
        run.model_hash_pin != pins.get("model_hash_pin")
        or run.gallery_revision_pin != pins.get("gallery_revision_pin")
        or run.threshold_id_pin != pins.get("threshold_id_pin")
    ):
        raise LabRunError("PIN_DRIFT", "Pin model/gallery/threshold đã đổi — lab run vô hiệu.")
    # Fresh recheck at promote time
    try:
        bound, fr = registry.get_frame(
            camera_id,
            require_live=True,
            for_biometric=True,
            allow_stale=False,
            max_age_s=MAX_FRAME_AGE_S,
        )
    except Exception as exc:
        raise LabRunError(
            getattr(exc, "code", "FRAME_ACCESS"),
            getattr(exc, "message_vi", str(exc)),
        ) from exc
    if bound.config_revision != run.config_revision:
        raise LabRunError("CONFIG_REVISION_CHANGED", "Config đổi trước khi promote.")
    if fr.width != run.decoded_w or fr.height != run.decoded_h:
        raise LabRunError("DIM_CHANGED", "Kích thước LIVE đổi trước khi promote.")

    known_n = unk_n = 0
    if run.kind == "FACE_PILOT":
        known_n = int(
            db.scalar(
                select(func.count())
                .select_from(FacePilotCaseEvent)
                .where(
                    FacePilotCaseEvent.lab_run_id == run.run_id,
                    FacePilotCaseEvent.truth_label.like("KNOWN:%"),
                )
            )
            or 0
        )
        unk_n = int(
            db.scalar(
                select(func.count())
                .select_from(FacePilotCaseEvent)
                .where(
                    FacePilotCaseEvent.lab_run_id == run.run_id,
                    FacePilotCaseEvent.truth_label == "UNKNOWN",
                )
            )
            or 0
        )
        if known_n < 1 or unk_n < 1:
            raise LabRunError("FACE_CASES_INSUFFICIENT", "Thiếu case server cho FACE_PILOT.")

    run.state = STATE_PHYSICAL
    run.verified_at = utc_now()
    ev = create_evidence(
        db,
        kind=run.kind,
        evidence_class=EVIDENCE_PHYSICAL,
        camera_id=camera_id,
        operator=operator,
        pins=pins,
        config_revision=run.config_revision,
        provenance=run.provenance,
        decoded_w=run.decoded_w,
        decoded_h=run.decoded_h,
        fps_measured=run.fps_measured,
        labeled_known=known_n,
        labeled_unknown=unk_n,
        frame_ids_json=run.frame_ids_json,
        note_vi=f"PHYSICAL từ lab_run={run.run_id}",
        ab_run_id="",
        lab_run_id=run.run_id,
    )
    db.flush()
    return ev


def revoke_lab_runs_for_camera(db: Session, *, camera_id: int, reason: str) -> int:
    n = 0
    for row in db.scalars(
        select(CameraLabRun).where(
            CameraLabRun.camera_id == camera_id, CameraLabRun.revoked.is_(False)
        )
    ).all():
        row.revoked = True
        row.state = STATE_REJECTED
        row.note_vi = (row.note_vi or "") + f" | REVOKED:{reason}"
        n += 1
    return n
