"""Tests for shared fetch strategy helpers."""

from __future__ import annotations

from datetime import date

from custom_components.uvi.fetch_strategy import (
    candidate_month_windows,
    candidate_window_days,
    discover_monthly_comparison_groups,
    latest_readout_date_from_payload,
    latest_readout_date_from_payloads,
    window_dates,
)
from tests.payload_samples import build_full_payload


def test_candidate_window_days_includes_today_day() -> None:
    days = candidate_window_days(date(2026, 3, 2))
    assert days == [1, 2, 3, 7, 14, 30]

    days_late_month = candidate_window_days(date(2026, 3, 31))
    assert days_late_month[-1] == 31


def test_window_dates_is_inclusive() -> None:
    from_date, to_date = window_dates(today=date(2026, 3, 2), days=3)
    assert from_date.isoformat() == "2026-02-28"
    assert to_date.isoformat() == "2026-03-02"


def test_candidate_month_windows() -> None:
    windows = candidate_month_windows(date(2026, 3, 2))
    assert windows[0] == ("2026-03-01", "2026-03-02", "current_month_to_date")
    assert windows[1] == ("2026-02-01", "2026-02-28", "previous_full_month")
    assert windows[2] == ("2026-01-01", "2026-01-31", "two_months_ago_full_month")


def test_discover_monthly_comparison_groups_from_payload() -> None:
    payload = build_full_payload()
    groups = discover_monthly_comparison_groups(payload)
    assert groups == ["h1", "h2", "k1", "w1"]


def test_latest_readout_helpers() -> None:
    payload = build_full_payload()

    heating_latest = latest_readout_date_from_payload(payload["heating"])
    warm_latest = latest_readout_date_from_payload(payload["warm_water"])
    cold_latest = latest_readout_date_from_payload(payload["cold_water"])
    overall_latest = latest_readout_date_from_payloads(
        [payload["heating"], payload["warm_water"], payload["cold_water"]]
    )

    assert heating_latest == date(2026, 2, 28)
    assert warm_latest == date(2026, 2, 28)
    assert cold_latest == date(2026, 2, 28)
    assert overall_latest == date(2026, 2, 28)
