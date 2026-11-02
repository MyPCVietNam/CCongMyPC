"""Server-issued CAMERA_LAB / FACE_PILOT runs with freshness + owner review state machine.

Evidence layers (do not conflate):
- LIVE_SOURCE_MEASURED: distinct LIVE frames + positive decoder FPS
- PHYSICAL_CONNECTIVITY_REVIEWED: owner ack of connectivity (CAMERA_LAB)
- FACE_PILOT_VALIDATION_APPROVED: supervised cases with CORRECT outcomes only
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.utc_time import to_utc_aware, utc_now
from app.models.entities import CameraLabRun, Employee, FacePilotCaseEvent, PilotEvidenceRecord
from app.services.evidence_store import EVIDENCE_PHYSICAL, create_evidence
from app.vision.faces.types import MatchOutcome

STATE_CREATED = "CREATED"
STATE_LIVE_MEASURED = "LIVE_MEASURED"
STATE_OWNER_REVIEWED = "OWNER_REVIEWED"
STATE_PHYSICAL = "PHYSICAL_VERIFIED"
STATE_REJECTED = "REJECTED"

MAX_FRAME_AGE_S = 3.0
RUN_TTL_HOURS = 8
MIN_DISTINCT_FRAMES = 3
MIN_OBS_WINDOW_S = 0.08  # distinct arrivals must span a real window (not instant duplicates)
MIN_FPS = 0.5
MEASURE_TIMEOUT_S = 8.0
POLL_SLEEP_S = 0.05
# Justified FACE_PILOT sample floor — NOT a claim of production accuracy.
MIN_CORRECT_KNOWN = 3
MIN_CORRECT_UNKNOWN = 3
MIN_DISTINCT_CASE_FRAMES = 6
MIN_DISTINCT_SUBJECTS = 2
CHALLENGE_MAX_FAILS = 5


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
        note_vi="Lab run server — chờ đo LIVE tươi (khung phân biệt + FPS > 0).",
        metrics_json=json.dumps(
            {
                "challenge_fail_count": 0,
                "face_validation_status": (
                    "N_A" if kind == "CAMERA_LAB" else "PENDING"
                ),
                "evidence_layers": {
                    "LIVE_SOURCE_MEASURED": False,
                    "PHYSICAL_CONNECTIVITY_REVIEWED": False,
                    "FACE_PILOT_VALIDATION_APPROVED": False,
                },
            },
            ensure_ascii=False,
        ),
    )
    db.add(run)
    db.flush()
    return run


def _metrics(run: CameraLabRun) -> dict[str, Any]:
    try:
        return json.loads(run.metrics_json or "{}")
    except json.JSONDecodeError:
        return {}


def _save_metrics(run: CameraLabRun, meta: dict[str, Any]) -> None:
    run.metrics_json = json.dumps(meta, ensure_ascii=False, sort_keys=True)


def _require_run(db: Session, run_id: str, camera_id: int) -> CameraLabRun:
    row = db.scalar(select(CameraLabRun).where(CameraLabRun.run_id == run_id))
    if row is None or row.camera_id != camera_id:
        raise LabRunError("LAB_RUN_NOT_FOUND", "Không tìm thấy lab run cho camera này.")
    if row.revoked:
        raise LabRunError("LAB_RUN_REVOKED", "Lab run đã thu hồi.")
    now = utc_now()
    expires = to_utc_aware(row.expires_at)
    if expires is not None and expires <= now:
        row.state = STATE_REJECTED
        raise LabRunError("LAB_RUN_EXPIRED", "Lab run đã hết hạn.")
    return row


def reveal_owner_challenge(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    operator: str,
) -> dict[str, str]:
    """Authenticated UI-only reveal — never log/print/persist outside the session response."""
    run = _require_run(db, run_id, camera_id)
    if run.state != STATE_LIVE_MEASURED:
        raise LabRunError("NEED_LIVE_MEASURED", "Challenge chỉ mở khi LIVE_MEASURED.")
    meta = _metrics(run)
    fails = int(meta.get("challenge_fail_count") or 0)
    if fails >= CHALLENGE_MAX_FAILS:
        raise LabRunError("CHALLENGE_LOCKED", "Quá nhiều lần sai — lab run bị khóa challenge.")
    # Audit that reveal happened without storing the secret in metrics
    meta["challenge_revealed_by"] = operator
    meta["challenge_revealed_at"] = utc_now().isoformat()
    _save_metrics(run, meta)
    db.flush()
    return {"run_id": run.run_id, "owner_challenge": run.owner_challenge or ""}


def measure_live_frames(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    registry: Any,
    samples: int = 5,
) -> CameraLabRun:
    """Capture DISTINCT CAMERA_LIVE frames — reject cached repeats / zero FPS."""
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

    need = max(MIN_DISTINCT_FRAMES, min(int(samples or MIN_DISTINCT_FRAMES), 15))
    frame_ids: list[str] = []
    widths: list[int] = []
    heights: list[int] = []
    ages: list[float] = []
    recv_times: list[float] = []
    seen: set[str] = set()
    deadline = time.monotonic() + MEASURE_TIMEOUT_S
    last_mono: float | None = None

    while len(frame_ids) < need:
        if time.monotonic() > deadline:
            raise LabRunError(
                "DISTINCT_FRAMES_TIMEOUT",
                f"Không thu đủ {need} khung phân biệt trong {MEASURE_TIMEOUT_S:.0f}s "
                f"(đã có {len(frame_ids)}). Không dùng khung cache lặp.",
            )
        try:
            bound2, fr = registry.get_frame(
                camera_id,
                require_live=True,
                for_biometric=True,
                allow_stale=False,
                max_age_s=MAX_FRAME_AGE_S,
            )
        except Exception as exc:
            code = getattr(exc, "code", "FRAME_ACCESS")
            raise LabRunError(str(code), getattr(exc, "message_vi", str(exc))) from exc
        if bound2.config_revision != bound.config_revision:
            raise LabRunError("CONFIG_CHANGED_MID_MEASURE", "Config đổi giữa lúc đo.")
        if not fr.frame_id:
            raise LabRunError("FRAME_ID_MISSING", "Thiếu frame_id từ decoder.")
        if fr.frame_id in seen:
            time.sleep(POLL_SLEEP_S)
            continue
        # Require real decoder receive_monotonic — do not fabricate with wall clock.
        if not getattr(fr, "receive_monotonic", None) or float(fr.receive_monotonic) <= 0:
            raise LabRunError(
                "RECV_MONOTONIC_MISSING",
                "Thiếu receive_monotonic từ nguồn — không bịa thời gian nhận.",
            )
        mono = float(fr.receive_monotonic)
        if last_mono is not None and mono <= last_mono:
            # Same or rewound clock with new id is still invalid for FPS
            time.sleep(POLL_SLEEP_S)
            continue
        age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
        if age < 0:
            raise LabRunError("NEGATIVE_FRAME_AGE", "Tuổi khung âm (lệch đồng hồ) — từ chối.")
        if age > MAX_FRAME_AGE_S:
            raise LabRunError("FRAME_TOO_OLD", f"Khung hình già {age:.2f}s.")
        if fr.width <= 0 or fr.height <= 0:
            raise LabRunError("EMPTY_FRAME", "Khung hình không có kích thước giải mã.")
        seen.add(fr.frame_id)
        frame_ids.append(fr.frame_id)
        widths.append(int(fr.width))
        heights.append(int(fr.height))
        ages.append(age * 1000.0)
        recv_times.append(mono)
        last_mono = mono
        time.sleep(POLL_SLEEP_S)

    for a, b in zip(recv_times, recv_times[1:]):
        if b <= a:
            raise LabRunError("NONMONOTONIC_RECV", "Thời gian nhận khung không tăng nghiêm ngặt.")

    window = recv_times[-1] - recv_times[0]
    if window < MIN_OBS_WINDOW_S:
        raise LabRunError(
            "OBS_WINDOW_TOO_SHORT",
            f"Cửa sổ quan sát {window:.3f}s quá ngắn để khẳng định FPS.",
        )
    fps = (len(recv_times) - 1) / window
    if fps < MIN_FPS:
        raise LabRunError(
            "FPS_TOO_LOW",
            f"FPS đo được {fps:.3f} < {MIN_FPS} — không PHYSICAL từ FPS=0/cache.",
        )

    w = widths[-1]
    h = heights[-1]
    if any(x != w for x in widths) or any(x != h for x in heights):
        raise LabRunError("UNSTABLE_DIMENSIONS", "Kích thước giải mã không ổn định trong cửa sổ đo.")

    health = bound.gateway.health()
    run.state = STATE_LIVE_MEASURED
    run.config_revision = bound.config_revision
    run.provenance = bound.provenance.value
    run.source_generation = bound.config_revision
    run.profile = bound.profile or run.profile
    run.decoded_w = w
    run.decoded_h = h
    run.fps_measured = float(fps)
    run.frame_age_ms = float(ages[-1])
    run.frame_ids_json = json.dumps(frame_ids)
    run.reconnect_count = int(getattr(health, "reconnect_count", 0) or 0)
    run.decode_errors = int(getattr(health, "decode_errors", 0) or 0)
    run.measured_at = utc_now()
    meta = _metrics(run)
    layers = dict(meta.get("evidence_layers") or {})
    layers["LIVE_SOURCE_MEASURED"] = True
    meta["evidence_layers"] = layers
    meta.update(
        {
            "samples_distinct": len(frame_ids),
            "decoded_w": w,
            "decoded_h": h,
            "fps_measured": fps,
            "obs_window_s": window,
            "frame_age_ms_last": ages[-1],
            "fps_kind": "DECODER_DISTINCT_ARRIVAL",
            "note": "SERVER_MEASURED_LIVE_DISTINCT",
        }
    )
    _save_metrics(run, meta)
    run.note_vi = "LIVE_SOURCE_MEASURED — khung phân biệt + FPS>0; chờ owner review."
    db.flush()
    return run


def _parse_known_employee_id(truth: str) -> int:
    parts = truth.split(":", 1)
    if len(parts) != 2 or parts[0] != "KNOWN":
        raise LabRunError("TRUTH_INVALID", "truth_label phải UNKNOWN hoặc KNOWN:<employee_id>.")
    try:
        return int(parts[1])
    except ValueError as exc:
        raise LabRunError("TRUTH_INVALID", "KNOWN employee_id phải là số nguyên.") from exc


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
    consent_ack_vi: str = "",
    supervised_by: str = "",
    subject_key: str = "",
) -> FacePilotCaseEvent:
    """Pull LIVE frame NOW and evaluate — client counts alone are insufficient."""
    run = _require_run(db, run_id, camera_id)
    if run.kind != "FACE_PILOT":
        raise LabRunError("NOT_FACE_PILOT_RUN", "Lab run không phải FACE_PILOT.")
    if run.state not in {STATE_LIVE_MEASURED, STATE_OWNER_REVIEWED}:
        raise LabRunError("NEED_LIVE_MEASURED", "Cần đo LIVE trước khi ghi case FACE_PILOT.")

    # Pin drift at case time
    if (
        run.model_hash_pin != (pins.get("model_hash_pin") or "")
        or run.gallery_revision_pin != (pins.get("gallery_revision_pin") or "")
        or run.threshold_id_pin != (pins.get("threshold_id_pin") or "")
    ):
        raise LabRunError("PIN_DRIFT", "Pin model/gallery/threshold đã đổi — từ chối case.")

    if not (consent_ack_vi or "").strip():
        raise LabRunError(
            "CONSENT_REQUIRED",
            "Mỗi case FACE_PILOT cần xác nhận đồng ý mẫu (consent_ack_vi).",
        )
    if not (supervised_by or "").strip():
        raise LabRunError(
            "SUPERVISION_REQUIRED",
            "Case cần supervised_by (toán tử giám sát đã xác thực).",
        )

    truth = (truth_label or "").strip().upper()
    if truth == "UNKNOWN":
        emp_id = None
    elif truth.startswith("KNOWN:"):
        emp_id = _parse_known_employee_id(truth)
    else:
        raise LabRunError("TRUTH_INVALID", "truth_label phải UNKNOWN hoặc KNOWN:<employee_id>.")

    if emp_id is not None:
        if not gallery_pairs:
            raise LabRunError(
                "GALLERY_EMPTY",
                "KNOWN truth yêu cầu gallery ACTIVE không rỗng — fail-closed.",
            )
        gallery_ids = {int(eid) for eid, _ in gallery_pairs}
        if emp_id not in gallery_ids:
            raise LabRunError(
                "KNOWN_NOT_IN_GALLERY",
                "KNOWN employee_id không có trong gallery ACTIVE.",
            )
        emp = db.get(Employee, emp_id)
        if emp is None or not bool(emp.active):
            raise LabRunError(
                "KNOWN_INACTIVE_OR_MISSING",
                "KNOWN employee_id không tồn tại hoặc không active.",
            )

    cond = (condition or "DAY").upper()
    if cond not in {"DAY", "DUSK", "NIGHT_IR", "BACKLIGHT"}:
        raise LabRunError("CONDITION_INVALID", "condition phải DAY|DUSK|NIGHT_IR|BACKLIGHT.")

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

    # Unique frame per case — no inflate by reusing one frame
    prior = db.scalar(
        select(func.count())
        .select_from(FacePilotCaseEvent)
        .where(
            FacePilotCaseEvent.lab_run_id == run.run_id,
            FacePilotCaseEvent.frame_id == fr.frame_id,
        )
    )
    if int(prior or 0) > 0:
        raise LabRunError(
            "DUPLICATE_CASE_FRAME",
            "frame_id đã dùng trong lab run — không đếm trùng để thổi số case.",
        )

    subj = (subject_key or "").strip()
    if not subj:
        # Pseudonymous default — not a real name
        subj = f"SUBJ:{hashlib.sha256(f'{run.run_id}:{truth}:{fr.frame_id}'.encode()).hexdigest()[:12]}"

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
        elif pred in {"UNKNOWN", "NO_FACE"}:
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
        condition=cond,
        native_face_width_px=int(q.face_width_px) if q and q.face_width_px else None,
        latency_ms=round(latency, 3),
        model_hash_pin=run.model_hash_pin,
        gallery_revision_pin=run.gallery_revision_pin,
        threshold_id_pin=run.threshold_id_pin,
        created_at=utc_now(),
        note_vi=(
            f"supervised_by={supervised_by}; subject_key={subj}; "
            f"consent=yes; lighting_operator_claim={cond}; no image/embedding stored."
        ),
    )
    db.add(case)
    db.flush()
    return case


def _face_pilot_report(db: Session, run: CameraLabRun) -> dict[str, Any]:
    cases = list(
        db.scalars(
            select(FacePilotCaseEvent).where(FacePilotCaseEvent.lab_run_id == run.run_id)
        ).all()
    )
    tallies = {
        "CORRECT": 0,
        "WRONG": 0,
        "FALSE_ACCEPT": 0,
        "MISS": 0,
        "AMBIGUOUS": 0,
        "NO_FACE": 0,
    }
    known_correct = 0
    unk_correct = 0
    frames: set[str] = set()
    subjects: set[str] = set()
    by_condition: dict[str, dict[str, int]] = {}
    for c in cases:
        tallies[c.outcome] = tallies.get(c.outcome, 0) + 1
        frames.add(c.frame_id)
        # subject from note if present
        subj = "unknown-subj"
        if "subject_key=" in (c.note_vi or ""):
            try:
                subj = (c.note_vi or "").split("subject_key=", 1)[1].split(";", 1)[0].strip()
            except IndexError:
                pass
        subjects.add(subj)
        if c.truth_label.startswith("KNOWN:") and c.outcome == "CORRECT":
            known_correct += 1
        if c.truth_label == "UNKNOWN" and c.outcome == "CORRECT":
            unk_correct += 1
        cond = c.condition or "DAY"
        by_condition.setdefault(cond, {})
        by_condition[cond][c.outcome] = by_condition[cond].get(c.outcome, 0) + 1

    blockers: list[str] = []
    if tallies.get("WRONG", 0) > 0:
        blockers.append("WRONG_IDENTITY")
    if tallies.get("FALSE_ACCEPT", 0) > 0:
        blockers.append("FALSE_ACCEPT")
    if known_correct < MIN_CORRECT_KNOWN:
        blockers.append("INSUFFICIENT_CORRECT_KNOWN")
    if unk_correct < MIN_CORRECT_UNKNOWN:
        blockers.append("INSUFFICIENT_CORRECT_UNKNOWN")
    if len(frames) < MIN_DISTINCT_CASE_FRAMES:
        blockers.append("INSUFFICIENT_DISTINCT_FRAMES")
    if len(subjects) < MIN_DISTINCT_SUBJECTS:
        blockers.append("INSUFFICIENT_DISTINCT_SUBJECTS")

    if blockers and (tallies.get("WRONG", 0) > 0 or tallies.get("FALSE_ACCEPT", 0) > 0):
        status = "FAILED"
    elif blockers:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "APPROVED"

    case_digest = hashlib.sha256()
    for c in sorted(cases, key=lambda x: x.case_id):
        case_digest.update(c.case_id.encode())
        case_digest.update(c.frame_id.encode())
        case_digest.update(c.truth_label.encode())
        case_digest.update(c.pred_label.encode())
        case_digest.update(c.outcome.encode())
        case_digest.update((c.model_hash_pin or "").encode())
        case_digest.update((c.gallery_revision_pin or "").encode())

    return {
        "status": status,
        "blockers": blockers,
        "tallies": tallies,
        "known_correct": known_correct,
        "unknown_correct": unk_correct,
        "distinct_frames": len(frames),
        "distinct_subjects": len(subjects),
        "by_condition": by_condition,
        "case_set_sha256": case_digest.hexdigest(),
        "sample_plan": {
            "min_correct_known": MIN_CORRECT_KNOWN,
            "min_correct_unknown": MIN_CORRECT_UNKNOWN,
            "min_distinct_frames": MIN_DISTINCT_CASE_FRAMES,
            "min_distinct_subjects": MIN_DISTINCT_SUBJECTS,
            "note_vi": (
                "Sàn mẫu tối thiểu cho pilot có giám sát — "
                "không phải tuyên bố độ chính xác sản xuất / 99%."
            ),
        },
        "claim": "FACE_PILOT_VALIDATION_APPROVED"
        if status == "APPROVED"
        else "NOT_BIOMETRIC_PASS",
    }


def owner_review(
    db: Session,
    *,
    run_id: str,
    camera_id: int,
    operator: str,
    challenge: str,
    ack_vi: str = "",
) -> CameraLabRun:
    """Single-operator acknowledgment (not independent two-party review)."""
    run = _require_run(db, run_id, camera_id)
    if run.state != STATE_LIVE_MEASURED:
        raise LabRunError("NEED_LIVE_MEASURED", "Owner review cần trạng thái LIVE_MEASURED.")
    meta = _metrics(run)
    fails = int(meta.get("challenge_fail_count") or 0)
    if fails >= CHALLENGE_MAX_FAILS:
        raise LabRunError("CHALLENGE_LOCKED", "Challenge đã khóa sau nhiều lần sai.")
    if not challenge or not secrets.compare_digest(challenge, run.owner_challenge or ""):
        meta["challenge_fail_count"] = fails + 1
        _save_metrics(run, meta)
        db.flush()
        raise LabRunError("CHALLENGE_INVALID", "Challenge owner không khớp — chống replay.")
    if not (ack_vi or "").strip():
        raise LabRunError(
            "ACK_REQUIRED",
            "Cần xác nhận tiếng Việt rõ ràng (ack_vi) — đây là xác nhận một toán tử, "
            "không phải review độc lập hai bên.",
        )

    face_report = None
    if run.kind == "FACE_PILOT":
        face_report = _face_pilot_report(db, run)
        meta["face_validation"] = face_report
        meta["face_validation_status"] = face_report["status"]
        if face_report["status"] == "FAILED":
            _save_metrics(run, meta)
            run.note_vi = "FACE_PILOT FAILED — WRONG/FALSE_ACCEPT; không duyệt sinh trắc."
            db.flush()
            raise LabRunError(
                "FACE_PILOT_OUTCOMES_FAILED",
                "Có WRONG hoặc FALSE_ACCEPT — không được coi là nhận diện đạt.",
            )
        if face_report["status"] == "INSUFFICIENT_EVIDENCE":
            _save_metrics(run, meta)
            run.note_vi = "FACE_PILOT INSUFFICIENT_EVIDENCE — chưa đủ mẫu CORRECT phân biệt."
            db.flush()
            raise LabRunError(
                "INSUFFICIENT_EVIDENCE",
                "Chưa đủ case CORRECT/khung/subject phân biệt — không PASS sinh trắc.",
            )
        layers = dict(meta.get("evidence_layers") or {})
        layers["FACE_PILOT_VALIDATION_APPROVED"] = True
        meta["evidence_layers"] = layers
    else:
        meta["face_validation_status"] = "N_A_CAMERA_LAB"

    layers = dict(meta.get("evidence_layers") or {})
    layers["PHYSICAL_CONNECTIVITY_REVIEWED"] = True
    meta["evidence_layers"] = layers
    meta["owner_ack_vi"] = ack_vi.strip()[:500]
    meta["review_kind"] = "SINGLE_OPERATOR_ACK"
    _save_metrics(run, meta)

    run.state = STATE_OWNER_REVIEWED
    run.owner_reviewed_by = operator
    run.owner_reviewed_at = utc_now()
    # one-time: rotate challenge after successful use
    run.owner_challenge = secrets.token_urlsafe(16)
    run.note_vi = (
        "PHYSICAL_CONNECTIVITY_REVIEWED (single-operator ack)."
        + (
            " FACE_PILOT_VALIDATION_APPROVED."
            if run.kind == "FACE_PILOT"
            else " CAMERA_LAB connectivity only — không phải FACE_PILOT accuracy."
        )
    )
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
    """PHYSICAL_VERIFIED only after OWNER_REVIEWED + fresh recheck (+ face validation)."""
    run = _require_run(db, run_id, camera_id)
    if run.state != STATE_OWNER_REVIEWED:
        raise LabRunError(
            "NEED_OWNER_REVIEW",
            "Không PHYSICAL_VERIFIED khi chưa OWNER_REVIEWED (EV11).",
        )
    if (
        run.model_hash_pin != pins.get("model_hash_pin")
        or run.gallery_revision_pin != pins.get("gallery_revision_pin")
        or run.threshold_id_pin != pins.get("threshold_id_pin")
    ):
        raise LabRunError("PIN_DRIFT", "Pin model/gallery/threshold đã đổi — lab run vô hiệu.")
    if run.fps_measured is None or float(run.fps_measured) < MIN_FPS:
        raise LabRunError("FPS_TOO_LOW", "FPS đo không hợp lệ — từ chối PHYSICAL.")

    meta = _metrics(run)
    layers = meta.get("evidence_layers") or {}
    if not layers.get("LIVE_SOURCE_MEASURED") or not layers.get("PHYSICAL_CONNECTIVITY_REVIEWED"):
        raise LabRunError("EVIDENCE_LAYERS_INCOMPLETE", "Thiếu lớp LIVE/connectivity.")

    known_n = unk_n = 0
    if run.kind == "FACE_PILOT":
        report = _face_pilot_report(db, run)
        meta["face_validation"] = report
        meta["face_validation_status"] = report["status"]
        if report["status"] != "APPROVED" or not layers.get("FACE_PILOT_VALIDATION_APPROVED"):
            _save_metrics(run, meta)
            db.flush()
            raise LabRunError(
                "FACE_PILOT_NOT_APPROVED",
                f"FACE_PILOT status={report['status']} — không PHYSICAL sinh trắc.",
            )
        # Recheck case pins match run
        bad_pin = db.scalar(
            select(func.count())
            .select_from(FacePilotCaseEvent)
            .where(
                FacePilotCaseEvent.lab_run_id == run.run_id,
                (
                    (FacePilotCaseEvent.model_hash_pin != run.model_hash_pin)
                    | (FacePilotCaseEvent.gallery_revision_pin != run.gallery_revision_pin)
                    | (FacePilotCaseEvent.threshold_id_pin != run.threshold_id_pin)
                ),
            )
        )
        if int(bad_pin or 0) > 0:
            raise LabRunError("CASE_PIN_MISMATCH", "Case gắn pin khác lab run — vô hiệu.")
        known_n = int(report["known_correct"])
        unk_n = int(report["unknown_correct"])

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

    _save_metrics(run, meta)
    run.state = STATE_PHYSICAL
    run.verified_at = utc_now()
    note = f"PHYSICAL từ lab_run={run.run_id}"
    if run.kind == "FACE_PILOT":
        note += f" face_status=APPROVED known_correct={known_n} unk_correct={unk_n}"
    else:
        note += " CAMERA_LAB connectivity PHYSICAL (not biometric accuracy)"
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
        note_vi=note,
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
