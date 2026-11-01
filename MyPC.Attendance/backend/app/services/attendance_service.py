"""Orchestrate observation → domain rules → persisted attendance events."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc, to_local
from app.core.settings import OperationalConfig
from app.domain.afternoon_selection import (
    AfternoonCandidate,
    AfternoonSelectionConfig,
    select_afternoon_reference,
)
from app.domain.leave_rules import LeaveExemption, LeaveKind, expectations
from app.domain.morning_rules import MorningConfig, evaluate_morning_observation
from app.models.entities import AttendanceEvent, LeaveRequest, RawObservation


class AttendanceService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def ingest_face_observation(
        self,
        session: Session,
        cfg: OperationalConfig,
        *,
        employee_id: int,
        work_date: date,
        observed_at_utc: datetime,
        observation_id: str,
        quality: float = 1.0,
        confidence: float = 1.0,
        source: str = "MOCK",
        camera_id: int | None = None,
        ambiguous: bool = False,
    ) -> dict:
        observed_at_utc = ensure_utc(observed_at_utc)
        local = to_local(observed_at_utc)
        leave = self._approved_leave(session, employee_id, work_date)
        exp = expectations(leave)

        raw = RawObservation(
            camera_id=camera_id,
            employee_id=employee_id,
            captured_at_utc=observed_at_utc,
            received_at_utc=self._clock.now_utc(),
            clock_trust="TRUSTED",
            obs_type="FACE_MATCH",
            source=source,
            quality=quality,
            confidence=confidence,
            immutable_metadata="{}",
        )
        session.add(raw)
        session.flush()

        # Morning path
        w = cfg.windows
        morning_end_excl = __import__(
            "app.domain.time_windows", fromlist=["morning_window_end_exclusive"]
        ).morning_window_end_exclusive(w.morning_recognition_end)
        from app.domain.time_windows import window_contains

        if window_contains(local, work_date, w.morning_recognition_start, morning_end_excl):
            return self._handle_morning(
                session,
                cfg,
                employee_id=employee_id,
                work_date=work_date,
                local=local,
                raw=raw,
                leave=leave,
                morning_required=exp.morning_required,
                ambiguous=ambiguous,
            )

        if window_contains(
            local,
            work_date,
            w.afternoon_recognition_start,
            w.afternoon_recognition_end_exclusive,
        ):
            return self._handle_afternoon(
                session,
                cfg,
                employee_id=employee_id,
                work_date=work_date,
                local=local,
                raw=raw,
                afternoon_required=exp.afternoon_reference_required,
                leave=leave,
            )

        return {
            "accepted": False,
            "reason": "OUTSIDE_WINDOWS",
            "message_vi": "Ngoài cửa sổ nhận diện",
            "observation_id": raw.id,
        }

    def _handle_morning(
        self,
        session: Session,
        cfg: OperationalConfig,
        *,
        employee_id: int,
        work_date: date,
        local: datetime,
        raw: RawObservation,
        leave: LeaveExemption | None,
        morning_required: bool,
        ambiguous: bool,
    ) -> dict:
        existing = session.scalar(
            select(AttendanceEvent).where(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.work_date == work_date,
                AttendanceEvent.event_type == "MORNING_CHECK_IN",
            )
        )
        mcfg = MorningConfig(
            work_date=work_date,
            window_start=cfg.windows.morning_recognition_start,
            window_end_inclusive=cfg.windows.morning_recognition_end,
            shift_start=cfg.windows.shift_start,
            late_tolerance_seconds=cfg.windows.late_tolerance_seconds,
            morning_leave_approved=bool(leave and leave.kind == LeaveKind.MORNING and leave.approved)
            or (leave is not None and leave.kind == LeaveKind.FULL_DAY and leave.approved)
            or not morning_required and leave is not None and leave.approved,
        )
        decision = evaluate_morning_observation(
            local,
            mcfg,
            existing_authoritative_at=existing.observed_at_utc if existing else None,
            ambiguous=ambiguous,
        )
        if decision.authoritative and existing is None:
            ev = AttendanceEvent(
                employee_id=employee_id,
                work_date=work_date,
                window_id="AM",
                event_type="MORNING_CHECK_IN",
                observed_at_utc=raw.captured_at_utc,
                source_observation_id=raw.id,
                recognition_version="p00",
                source=raw.source,
                status=decision.status.value,
                late_seconds=decision.late_seconds,
                note_vi=decision.message_vi,
            )
            session.add(ev)
            session.flush()
            return {
                "accepted": True,
                "event_type": "MORNING_CHECK_IN",
                "status": decision.status.value,
                "observed_at_utc": raw.captured_at_utc.isoformat(),
                "late_seconds": decision.late_seconds,
                "message_vi": decision.message_vi,
                "event_id": ev.id,
            }
        return {
            "accepted": False,
            "event_type": "MORNING_CHECK_IN",
            "status": decision.status.value,
            "message_vi": decision.message_vi,
            "late_seconds": decision.late_seconds,
        }

    def _handle_afternoon(
        self,
        session: Session,
        cfg: OperationalConfig,
        *,
        employee_id: int,
        work_date: date,
        local: datetime,
        raw: RawObservation,
        afternoon_required: bool,
        leave: LeaveExemption | None,
    ) -> dict:
        # Collect today's PM observations for this employee from DB
        rows = session.scalars(
            select(RawObservation).where(
                RawObservation.employee_id == employee_id,
                RawObservation.obs_type == "FACE_MATCH",
            )
        ).all()
        sel_cfg = AfternoonSelectionConfig(
            work_date=work_date,
            window_start=cfg.windows.afternoon_recognition_start,
            window_end_exclusive=cfg.windows.afternoon_recognition_end_exclusive,
            reference_time=cfg.windows.afternoon_selection.reference_time,
            near_before_minutes=cfg.windows.afternoon_selection.near_tolerance_before_minutes,
            near_after_minutes=cfg.windows.afternoon_selection.near_tolerance_after_minutes,
            preferred_photo_start=cfg.windows.afternoon_selection.preferred_photo_start,
            preferred_photo_end=cfg.windows.afternoon_selection.preferred_photo_end,
            selection_policy_version=cfg.windows.afternoon_selection.selection_policy_version,
            afternoon_leave_approved=not afternoon_required,
        )
        from app.domain.time_windows import window_contains

        candidates: list[AfternoonCandidate] = []
        for r in rows:
            captured = ensure_utc(r.captured_at_utc)
            loc = to_local(captured)
            if window_contains(
                loc,
                work_date,
                cfg.windows.afternoon_recognition_start,
                cfg.windows.afternoon_recognition_end_exclusive,
            ):
                candidates.append(
                    AfternoonCandidate(
                        observation_id=str(r.id),
                        observed_at_local=loc,
                        quality=r.quality,
                        confidence=r.confidence,
                    )
                )

        result = select_afternoon_reference(candidates, sel_cfg)

        existing = session.scalar(
            select(AttendanceEvent).where(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.work_date == work_date,
                AttendanceEvent.event_type == "AFTERNOON_REFERENCE",
            )
        )

        if result.selected is None:
            return {
                "accepted": True,
                "event_type": "AFTERNOON_OBSERVATION",
                "status": result.status.value,
                "message_vi": result.message_vi,
                "afternoon_first_observed_at": (
                    result.first_observed.observed_at_local.isoformat()
                    if result.first_observed
                    else None
                ),
                "afternoon_reference_observed_at": None,
                "review_required": result.review_required,
            }

        # Update or create single AFTERNOON_REFERENCE (improves until finalized)
        selected_raw_id = int(result.selected.observation_id)
        photo_at = (
            result.preferred_photo.observed_at_local if result.preferred_photo else None
        )
        first_at = (
            result.first_observed.observed_at_local if result.first_observed else None
        )

        # Convert local back — store UTC of selected observation
        selected_row = session.get(RawObservation, selected_raw_id)
        assert selected_row is not None

        if existing is None:
            ev = AttendanceEvent(
                employee_id=employee_id,
                work_date=work_date,
                window_id="PM",
                event_type="AFTERNOON_REFERENCE",
                observed_at_utc=selected_row.captured_at_utc,
                source_observation_id=selected_row.id,
                recognition_version="p00",
                selection_status=result.status.value,
                selection_policy_version=result.selection_policy_version,
                photo_captured_at_utc=self._local_to_utc(photo_at) if photo_at else None,
                first_observed_at_utc=self._local_to_utc(first_at) if first_at else None,
                source=raw.source,
                status="PROVISIONAL",
                review_required=result.review_required,
                note_vi=result.message_vi,
                leave_exemption_id=None,
            )
            session.add(ev)
            session.flush()
            event_id = ev.id
        else:
            existing.observed_at_utc = selected_row.captured_at_utc
            existing.source_observation_id = selected_row.id
            existing.selection_status = result.status.value
            existing.selection_policy_version = result.selection_policy_version
            existing.photo_captured_at_utc = (
                self._local_to_utc(photo_at) if photo_at else None
            )
            existing.first_observed_at_utc = (
                self._local_to_utc(first_at) if first_at else None
            )
            existing.review_required = result.review_required
            existing.note_vi = result.message_vi
            existing.status = "PROVISIONAL"
            session.flush()
            event_id = existing.id

        # Safeguard: never store exactly forced 18:00 unless observation was at 18:00
        observed_local = to_local(ensure_utc(selected_row.captured_at_utc))
        return {
            "accepted": True,
            "event_type": "AFTERNOON_REFERENCE",
            "event_id": event_id,
            "status": result.status.value,
            "message_vi": result.message_vi,
            "afternoon_first_observed_at": first_at.isoformat() if first_at else None,
            "afternoon_reference_observed_at": observed_local.isoformat(),
            "afternoon_primary_photo_captured_at": photo_at.isoformat() if photo_at else None,
            "reference_anchor_local": result.reference_anchor_local.isoformat(),
            "review_required": result.review_required,
            "fabricated_18_00": False,
        }

    def _approved_leave(
        self, session: Session, employee_id: int, work_date: date
    ) -> LeaveExemption | None:
        row = session.scalar(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.work_date == work_date,
                LeaveRequest.status == "APPROVED",
            )
        )
        if row is None:
            return None
        return LeaveExemption(kind=LeaveKind(row.kind), approved=True)

    @staticmethod
    def _local_to_utc(dt: datetime) -> datetime:
        return dt.astimezone(__import__("datetime").timezone.utc)
