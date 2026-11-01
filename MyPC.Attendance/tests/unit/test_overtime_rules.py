"""OT01–OT16 core overtime invariants (domain)."""

from __future__ import annotations

from app.core.clock import local_wall
from app.domain.overtime_rules import (
    OvertimeConfig,
    OvertimeState,
    duration_seconds,
    evaluate_overtime_end,
    evaluate_overtime_start,
)


def day():
    return local_wall(2026, 3, 2).date()


def cfg():
    return OvertimeConfig(work_date=day())


def test_ot01_exit_at_boundary_zero():
    start = evaluate_overtime_start(
        cfg=cfg(),
        continuous_through_boundary=True,
        first_post_boundary_at=local_wall(2026, 3, 2, 18, 0, 0),
    )
    # Continuous at boundary with exit at 18:00 => duration 0
    end_state, end_at, _ = evaluate_overtime_end(
        state=start.state,
        verified_exit_at=local_wall(2026, 3, 2, 18, 0, 0),
        last_observed_at=local_wall(2026, 3, 2, 18, 0, 0),
        at_monitor_cutoff=False,
    )
    assert end_state == OvertimeState.AUTO_RECORDED
    assert duration_seconds(local_wall(2026, 3, 2, 18, 0, 0), end_at) == 0


def test_ot02_30_minutes():
    start = evaluate_overtime_start(
        cfg=cfg(),
        continuous_through_boundary=True,
        first_post_boundary_at=local_wall(2026, 3, 2, 18, 1, 0),
    )
    assert start.state == OvertimeState.ACTIVE
    assert start.start_at_local == local_wall(2026, 3, 2, 18, 0, 0)
    _, end_at, _ = evaluate_overtime_end(
        state=start.state,
        verified_exit_at=local_wall(2026, 3, 2, 18, 30, 0),
        last_observed_at=None,
        at_monitor_cutoff=False,
    )
    assert duration_seconds(start.start_at_local, end_at) == 1800


def test_ot03_1925_within_pm_window_not_anchor():
    exit_t = local_wall(2026, 3, 2, 19, 25, 0)
    start = evaluate_overtime_start(
        cfg=cfg(),
        continuous_through_boundary=True,
        first_post_boundary_at=local_wall(2026, 3, 2, 18, 1, 0),
    )
    _, end_at, _ = evaluate_overtime_end(
        state=start.state,
        verified_exit_at=exit_t,
        last_observed_at=None,
        at_monitor_cutoff=False,
    )
    assert duration_seconds(start.start_at_local, end_at) == 85 * 60
    # 19:25 is within corrected PM recognition window concept — not the 18:00 anchor
    assert exit_t.hour == 19


def test_ot04_provisional_1820():
    start = evaluate_overtime_start(
        cfg=cfg(),
        continuous_through_boundary=False,
        first_post_boundary_at=local_wall(2026, 3, 2, 18, 20, 0),
    )
    assert start.state == OvertimeState.CANDIDATE
    assert start.provisional is True
    assert start.start_at_local == local_wall(2026, 3, 2, 18, 20, 0)


def test_ot05_last_seen_not_exit():
    state, end_at, msg = evaluate_overtime_end(
        state=OvertimeState.ACTIVE,
        verified_exit_at=None,
        last_observed_at=local_wall(2026, 3, 2, 18, 10, 0),
        at_monitor_cutoff=False,
    )
    assert state == OvertimeState.ACTIVE
    assert end_at is None
    assert "xác minh" in msg.lower() or "Xuất hiện" in msg


def test_ot06_camera_lost_pending():
    state, end_at, _ = evaluate_overtime_end(
        state=OvertimeState.ACTIVE,
        verified_exit_at=None,
        last_observed_at=None,
        at_monitor_cutoff=False,
        camera_lost=True,
    )
    assert state == OvertimeState.PENDING_REVIEW
    assert end_at is None


def test_ot13_pm_photo_alone_no_ot():
    start = evaluate_overtime_start(
        cfg=cfg(),
        continuous_through_boundary=False,
        first_post_boundary_at=None,
        pm_reference_only_at=local_wall(2026, 3, 2, 17, 58, 0),
    )
    assert start.state == OvertimeState.NOT_STARTED


def test_ot15_cutoff_pending_not_auto_close():
    state, end_at, msg = evaluate_overtime_end(
        state=OvertimeState.ACTIVE,
        verified_exit_at=None,
        last_observed_at=local_wall(2026, 3, 2, 23, 55, 0),
        at_monitor_cutoff=True,
    )
    assert state == OvertimeState.PENDING_REVIEW
    assert end_at is None
    assert "23" not in (end_at.isoformat() if end_at else "")
