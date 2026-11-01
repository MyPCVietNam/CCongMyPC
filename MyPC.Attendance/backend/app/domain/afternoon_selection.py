"""
v1.5 afternoon reference selection.

Window: [17:00:00, 23:56:00) local — includes 23:55:59.999, excludes 23:56:00.
Reference anchor 18:00 is a selection preference, NEVER a fabricated observation time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from app.domain.time_windows import (
    LOCAL_TZ,
    abs_seconds_from_anchor,
    combine_local,
    parse_hms,
    window_contains,
)


class AfternoonSelectionStatus(str, Enum):
    EXACT_REFERENCE = "EXACT_REFERENCE"
    NEAR_REFERENCE = "NEAR_REFERENCE"
    EARLIER_FALLBACK = "EARLIER_FALLBACK"
    AFTERNOON_LATE_FALLBACK = "AFTERNOON_LATE_FALLBACK"
    NO_OBSERVATION = "NO_OBSERVATION"
    EXEMPT_LEAVE = "EXEMPT_LEAVE"


@dataclass(frozen=True, slots=True)
class AfternoonCandidate:
    observation_id: str
    observed_at_local: datetime
    quality: float = 1.0
    confidence: float = 1.0
    photo_eligible: bool = True


@dataclass(frozen=True, slots=True)
class AfternoonSelectionResult:
    status: AfternoonSelectionStatus
    selected: AfternoonCandidate | None
    first_observed: AfternoonCandidate | None
    preferred_photo: AfternoonCandidate | None
    reference_anchor_local: datetime
    selection_policy_version: str
    review_required: bool
    message_vi: str


@dataclass(frozen=True, slots=True)
class AfternoonSelectionConfig:
    work_date: date
    window_start: str = "17:00:00"
    window_end_exclusive: str = "23:56:00"
    reference_time: str = "18:00:00"
    near_before_minutes: int = 5
    near_after_minutes: int = 5
    preferred_photo_start: str = "17:55:00"
    preferred_photo_end: str = "18:00:00"
    selection_policy_version: str = "v1.5-nearest-earlier-fallback"
    afternoon_leave_approved: bool = False


def _in_window(c: AfternoonCandidate, cfg: AfternoonSelectionConfig) -> bool:
    return window_contains(
        c.observed_at_local, cfg.work_date, cfg.window_start, cfg.window_end_exclusive
    )


def _sort_key_near(c: AfternoonCandidate, cfg: AfternoonSelectionConfig) -> tuple:
    """Smallest abs distance; earlier on tie; higher quality/confidence; stable id."""
    dist = abs_seconds_from_anchor(c.observed_at_local, cfg.work_date, cfg.reference_time)
    local = c.observed_at_local.astimezone(LOCAL_TZ)
    # earlier = smaller timestamp → sort ascending on local for tie
    return (dist, local.timestamp(), -c.quality, -c.confidence, c.observation_id)


def select_afternoon_reference(
    candidates: list[AfternoonCandidate],
    cfg: AfternoonSelectionConfig,
) -> AfternoonSelectionResult:
    anchor = combine_local(cfg.work_date, parse_hms(cfg.reference_time))

    if cfg.afternoon_leave_approved:
        in_window = [c for c in candidates if _in_window(c, cfg)]
        first = min(in_window, key=lambda c: c.observed_at_local) if in_window else None
        return AfternoonSelectionResult(
            status=AfternoonSelectionStatus.EXEMPT_LEAVE,
            selected=None,
            first_observed=first,
            preferred_photo=None,
            reference_anchor_local=anchor,
            selection_policy_version=cfg.selection_policy_version,
            review_required=bool(in_window),
            message_vi="Nghỉ phép buổi chiều đã duyệt"
            + (" — có quan sát thực tế cần đối soát" if in_window else ""),
        )

    eligible = [c for c in candidates if _in_window(c, cfg)]
    if not eligible:
        return AfternoonSelectionResult(
            status=AfternoonSelectionStatus.NO_OBSERVATION,
            selected=None,
            first_observed=None,
            preferred_photo=None,
            reference_anchor_local=anchor,
            selection_policy_version=cfg.selection_policy_version,
            review_required=True,
            message_vi="Chưa có nhận diện chiều",
        )

    first = min(eligible, key=lambda c: (c.observed_at_local, c.observation_id))

    # Exact reference: same local wall second as anchor (microseconds ignored for "exact 18:00:00")
    anchor_second = anchor.replace(microsecond=0)
    exact = [
        c
        for c in eligible
        if c.observed_at_local.astimezone(LOCAL_TZ).replace(microsecond=0) == anchor_second
    ]

    selected: AfternoonCandidate | None = None
    status: AfternoonSelectionStatus
    review = False

    if exact:
        selected = sorted(exact, key=lambda c: (-c.quality, -c.confidence, c.observation_id))[0]
        status = AfternoonSelectionStatus.EXACT_REFERENCE
    else:
        near_start = anchor - timedelta(minutes=cfg.near_before_minutes)
        near_end = anchor + timedelta(minutes=cfg.near_after_minutes)
        near = [
            c
            for c in eligible
            if near_start <= c.observed_at_local.astimezone(LOCAL_TZ) <= near_end
        ]
        if near:
            selected = sorted(near, key=lambda c: _sort_key_near(c, cfg))[0]
            status = AfternoonSelectionStatus.NEAR_REFERENCE
        else:
            earlier = [
                c
                for c in eligible
                if c.observed_at_local.astimezone(LOCAL_TZ) < anchor
            ]
            if earlier:
                # Latest valid sample before 18:00; tie → higher quality/confidence → stable id
                by_time: dict[datetime, list[AfternoonCandidate]] = {}
                for c in earlier:
                    t = c.observed_at_local.astimezone(LOCAL_TZ)
                    by_time.setdefault(t, []).append(c)
                latest_t = max(by_time.keys())
                selected = sorted(
                    by_time[latest_t],
                    key=lambda c: (-c.quality, -c.confidence, c.observation_id),
                )[0]
                status = AfternoonSelectionStatus.EARLIER_FALLBACK
            else:
                later = [
                    c
                    for c in eligible
                    if c.observed_at_local.astimezone(LOCAL_TZ) > anchor
                ]
                selected = min(
                    later,
                    key=lambda c: (
                        c.observed_at_local.astimezone(LOCAL_TZ),
                        -c.quality,
                        -c.confidence,
                        c.observation_id,
                    ),
                )
                status = AfternoonSelectionStatus.AFTERNOON_LATE_FALLBACK
                review = True

    preferred_photo = _select_preferred_photo(eligible, selected, cfg)

    msg = {
        AfternoonSelectionStatus.EXACT_REFERENCE: "Đã ghi nhận điểm danh chiều (đúng mốc 18:00)",
        AfternoonSelectionStatus.NEAR_REFERENCE: "Đã ghi nhận điểm danh chiều",
        AfternoonSelectionStatus.EARLIER_FALLBACK: "Đã ghi nhận điểm danh chiều (mẫu trước 18:00)",
        AfternoonSelectionStatus.AFTERNOON_LATE_FALLBACK: "Đã ghi nhận điểm danh chiều — Cần đối soát",
    }[status]

    # Never rewrite an observation timestamp to the 18:00 anchor.
    assert selected is not None
    selected_local = selected.observed_at_local.astimezone(LOCAL_TZ)
    if status == AfternoonSelectionStatus.EXACT_REFERENCE:
        assert selected_local.replace(microsecond=0) == anchor.replace(microsecond=0)
    else:
        # Selected stamp must remain the real capture time (not forced to 18:00).
        assert selected_local.replace(microsecond=0) != anchor.replace(microsecond=0)

    return AfternoonSelectionResult(
        status=status,
        selected=selected,
        first_observed=first,
        preferred_photo=preferred_photo,
        reference_anchor_local=anchor,
        selection_policy_version=cfg.selection_policy_version,
        review_required=review,
        message_vi=msg,
    )


def _select_preferred_photo(
    eligible: list[AfternoonCandidate],
    selected: AfternoonCandidate,
    cfg: AfternoonSelectionConfig,
) -> AfternoonCandidate:
    photo_start = combine_local(cfg.work_date, parse_hms(cfg.preferred_photo_start))
    photo_end = combine_local(cfg.work_date, parse_hms(cfg.preferred_photo_end))
    # Prefer clearest in [17:55, 18:00]
    band = [
        c
        for c in eligible
        if c.photo_eligible
        and photo_start <= c.observed_at_local.astimezone(LOCAL_TZ) <= photo_end
    ]
    if band:
        return sorted(band, key=lambda c: (-c.quality, -c.confidence, c.observation_id))[0]
    # Fallback: authorized evidence linked to chosen reference
    return selected
