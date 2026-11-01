"""AM01–AM11 morning boundary cases."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.clock import local_wall
from app.domain.morning_rules import MorningConfig, MorningStatus, evaluate_morning_observation


@pytest.fixture
def day():
    return local_wall(2026, 3, 2).date()


@pytest.fixture
def cfg(day):
    return MorningConfig(work_date=day)


def test_am01_outside_before(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 14, 59, 999000)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.OUTSIDE_WINDOW
    assert d.authoritative is False


def test_am02_early_window_start(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 15, 0)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.EARLY_ARRIVAL
    assert d.authoritative is True


def test_am03_before_shift(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 29, 59)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.EARLY_ARRIVAL
    assert d.late_seconds == 0


def test_am04_on_time(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 30, 0)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.ON_TIME
    assert d.late_seconds == 0


def test_am05_late_1ms(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 30, 0, 1000)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.LATE
    assert d.late_seconds == pytest.approx(0.001)
    assert d.late_seconds > 0


def test_am06_ten_minutes_late(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 40, 0)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.LATE
    assert d.late_seconds == pytest.approx(600.0)


def test_am07_end_of_window(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 45, 0, 999000)
    d = evaluate_morning_observation(obs, cfg)
    assert d.authoritative is True
    assert d.status == MorningStatus.LATE


def test_am08_outside_after(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 45, 1)
    d = evaluate_morning_observation(obs, cfg)
    assert d.status == MorningStatus.OUTSIDE_WINDOW


def test_am09_first_wins(cfg, day):
    first = local_wall(day.year, day.month, day.day, 8, 20, 0)
    second = local_wall(day.year, day.month, day.day, 8, 35, 0)
    d1 = evaluate_morning_observation(first, cfg)
    d2 = evaluate_morning_observation(second, cfg, existing_authoritative_at=first)
    assert d1.authoritative is True
    assert d2.status == MorningStatus.DUPLICATE_IGNORED
    assert d2.observed_at_local == first


def test_am11_ambiguous(cfg, day):
    obs = local_wall(day.year, day.month, day.day, 8, 20, 0)
    d = evaluate_morning_observation(obs, cfg, ambiguous=True)
    assert d.status == MorningStatus.AMBIGUOUS
    assert d.authoritative is False
