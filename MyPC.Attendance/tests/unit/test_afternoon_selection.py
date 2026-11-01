"""PM01–PM20 afternoon 17:00–23:55 and 18:00 reference selection (v1.5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.clock import local_wall
from app.domain.afternoon_selection import (
    AfternoonCandidate,
    AfternoonSelectionConfig,
    AfternoonSelectionStatus,
    select_afternoon_reference,
)
from app.domain.time_windows import window_contains


@pytest.fixture
def day():
    return local_wall(2026, 3, 2).date()


@pytest.fixture
def cfg(day):
    return AfternoonSelectionConfig(work_date=day)


def cand(day, h, m, s=0, us=0, oid="a", quality=1.0):
    return AfternoonCandidate(
        observation_id=oid,
        observed_at_local=local_wall(day.year, day.month, day.day, h, m, s, us),
        quality=quality,
        confidence=1.0,
    )


def test_pm01_outside_before(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 16, 59, 59, 999000)
    assert not window_contains(obs, day, "17:00:00", "23:56:00")
    result = select_afternoon_reference([cand(day, 16, 59, 59, 999000)], cfg)
    assert result.status == AfternoonSelectionStatus.NO_OBSERVATION
    assert result.selected is None


def test_pm02_window_start_included(cfg, day):
    result = select_afternoon_reference([cand(day, 17, 0, 0, oid="first")], cfg)
    assert result.first_observed is not None
    assert result.selected is not None
    assert result.selected.observed_at_local.hour == 17
    assert result.status == AfternoonSelectionStatus.EARLIER_FALLBACK


def test_pm03_end_of_2355_included_2356_excluded(cfg, day):
    inside = local_wall(day.year, day.month, day.day, 23, 55, 59, 999000)
    outside = local_wall(day.year, day.month, day.day, 23, 56, 0)
    assert window_contains(inside, day, "17:00:00", "23:56:00")
    assert not window_contains(outside, day, "17:00:00", "23:56:00")
    # Must NOT use old 19:00 cutoff
    late = local_wall(day.year, day.month, day.day, 21, 0, 0)
    assert window_contains(late, day, "17:00:00", "23:56:00")
    assert not window_contains(late, day, "17:00:00", "19:00:00")


def test_pm04_exact_1800(cfg, day):
    result = select_afternoon_reference([cand(day, 18, 0, 0, oid="exact")], cfg)
    assert result.status == AfternoonSelectionStatus.EXACT_REFERENCE
    assert result.selected is not None
    assert result.selected.observed_at_local == local_wall(day.year, day.month, day.day, 18, 0, 0)
    # Never rewrite — equals real observation
    assert result.selected.observed_at_local == result.reference_anchor_local


def test_pm05_closer_1757_vs_1804(cfg, day):
    result = select_afternoon_reference(
        [cand(day, 17, 57, oid="a"), cand(day, 18, 4, oid="b")], cfg
    )
    assert result.selected is not None
    assert result.selected.observation_id == "a"
    assert result.status == AfternoonSelectionStatus.NEAR_REFERENCE


def test_pm06_tie_earlier(cfg, day):
    result = select_afternoon_reference(
        [cand(day, 17, 59, oid="a"), cand(day, 18, 1, oid="b")], cfg
    )
    assert result.selected is not None
    assert result.selected.observation_id == "a"


def test_pm07_earlier_fallback_latest(cfg, day):
    result = select_afternoon_reference(
        [cand(day, 17, 10, oid="a"), cand(day, 17, 40, oid="b")], cfg
    )
    assert result.status == AfternoonSelectionStatus.EARLIER_FALLBACK
    assert result.selected is not None
    assert result.selected.observation_id == "b"


def test_pm08_late_fallback_real_1820_not_fabricated_1800(cfg, day):
    result = select_afternoon_reference(
        [cand(day, 18, 20, oid="a"), cand(day, 21, 0, oid="b")], cfg
    )
    assert result.status == AfternoonSelectionStatus.AFTERNOON_LATE_FALLBACK
    assert result.selected is not None
    assert result.selected.observation_id == "a"
    assert result.selected.observed_at_local.hour == 18
    assert result.selected.observed_at_local.minute == 20
    assert result.review_required is True
    # NEVER manufacture 18:00
    assert result.selected.observed_at_local != result.reference_anchor_local


def test_pm09_separate_first_reference_photo(cfg, day):
    # Photos ranked by quality in [17:55,18:00]; reference by nearest-to-18:00.
    # 17:59 is closer → official reference; 17:57 has clearer quality → preferred photo.
    result = select_afternoon_reference(
        [
            cand(day, 17, 10, oid="first", quality=0.5),
            cand(day, 17, 57, oid="photo", quality=1.0),
            cand(day, 17, 59, oid="ref", quality=0.7),
        ],
        cfg,
    )
    assert result.selected is not None
    assert result.selected.observation_id == "ref"
    assert result.first_observed is not None
    assert result.first_observed.observation_id == "first"
    assert result.preferred_photo is not None
    assert result.preferred_photo.observation_id == "photo"
    assert result.selected.observation_id != result.first_observed.observation_id


def test_pm10_photo_fallback(cfg, day):
    result = select_afternoon_reference(
        [cand(day, 17, 40, oid="only", quality=0.8)], cfg
    )
    assert result.preferred_photo is not None
    assert result.preferred_photo.observation_id == "only"


def test_pm11_recognition_alive_after_1800(cfg, day):
    # 21:30 still in window — late fallback selection but engine stays alive
    result = select_afternoon_reference([cand(day, 21, 30, oid="late")], cfg)
    assert result.selected is not None
    assert result.selected.observed_at_local.hour == 21
    assert window_contains(
        local_wall(day.year, day.month, day.day, 22, 10), day, "17:00:00", "23:56:00"
    )


def test_pm12_one_official_reference(cfg, day):
    many = [cand(day, h, m, oid=f"{h}{m}") for h in range(17, 24) for m in (0, 30)]
    many = [c for c in many if window_contains(c.observed_at_local, day, "17:00:00", "23:56:00")]
    result = select_afternoon_reference(many, cfg)
    assert result.selected is not None
    # Single selection object
    assert isinstance(result.selected.observation_id, str)


def test_pm13_morning_leave_does_not_exempt_pm(cfg, day):
    # afternoon_leave_approved False → still selects
    result = select_afternoon_reference([cand(day, 17, 58, oid="x")], cfg)
    assert result.selected is not None
    assert result.status != AfternoonSelectionStatus.EXEMPT_LEAVE


def test_pm14_afternoon_leave_exempt(cfg, day):
    leave_cfg = AfternoonSelectionConfig(work_date=day, afternoon_leave_approved=True)
    result = select_afternoon_reference([cand(day, 17, 30, oid="seen")], leave_cfg)
    assert result.status == AfternoonSelectionStatus.EXEMPT_LEAVE
    assert result.selected is None
    assert result.first_observed is not None  # preserve actual observation
    assert "Nghỉ phép buổi chiều đã duyệt" in result.message_vi


def test_pm15_full_day_no_synth(cfg, day):
    leave_cfg = AfternoonSelectionConfig(work_date=day, afternoon_leave_approved=True)
    result = select_afternoon_reference([], leave_cfg)
    assert result.selected is None
    assert result.status == AfternoonSelectionStatus.EXEMPT_LEAVE


def test_pm17_no_observation_needs_review(cfg, day):
    result = select_afternoon_reference([], cfg)
    assert result.status == AfternoonSelectionStatus.NO_OBSERVATION
    assert result.review_required is True
    assert result.selected is None


def test_pm18_2355_not_ot_proof(cfg, day):
    result = select_afternoon_reference([cand(day, 23, 55, 30, oid="x")], cfg)
    assert result.selected is not None
    # Selection is late fallback — OT engine must not auto-credit from this alone
    assert result.status == AfternoonSelectionStatus.AFTERNOON_LATE_FALLBACK


def test_pm20_unordered_ingestion_stable(cfg, day):
    a = [cand(day, 17, 57, oid="a"), cand(day, 18, 4, oid="b")]
    b = list(reversed(a))
    r1 = select_afternoon_reference(a, cfg)
    r2 = select_afternoon_reference(b, cfg)
    assert r1.selected is not None and r2.selected is not None
    assert r1.selected.observation_id == r2.selected.observation_id == "a"


def test_no_19_00_default_in_config(cfg):
    assert cfg.window_end_exclusive == "23:56:00"
    assert cfg.window_end_exclusive != "19:00:00"
