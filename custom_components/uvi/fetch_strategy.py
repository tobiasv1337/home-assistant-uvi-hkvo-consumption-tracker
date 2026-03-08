"""Shared fetch strategy helpers for adaptive UVI data retrieval."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

from .const import ADAPTIVE_WINDOW_CANDIDATE_DAYS


def candidate_window_days(today: date) -> list[int]:
    """Return increasing adaptive candidate windows in days."""
    values: list[int] = []

    for days in ADAPTIVE_WINDOW_CANDIDATE_DAYS:
        normalized = max(1, int(days))
        if normalized not in values:
            values.append(normalized)

    if today.day not in values:
        values.append(today.day)

    return sorted(values)


def window_dates(today: date, days: int) -> tuple[date, date]:
    """Return an inclusive [from, to] date window ending today."""
    normalized = max(1, days)
    from_date = today - timedelta(days=normalized - 1)
    return from_date, today


def candidate_month_windows(today: date) -> list[tuple[str, str, str]]:
    """Return robust month windows for portal probing."""
    this_month_start = today.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev2_month_end = prev_month_start - timedelta(days=1)
    prev2_month_start = prev2_month_end.replace(day=1)

    return [
        (
            this_month_start.isoformat(),
            today.isoformat(),
            "current_month_to_date",
        ),
        (
            prev_month_start.isoformat(),
            prev_month_end.isoformat(),
            "previous_full_month",
        ),
        (
            prev2_month_start.isoformat(),
            prev2_month_end.isoformat(),
            "two_months_ago_full_month",
        ),
    ]


def discover_monthly_comparison_groups(payload: Mapping[str, Any]) -> list[str]:
    """Discover monthly-comparison groups from endpoint payloads."""
    groups: set[str] = set()

    _collect_groups_from_summary(payload.get("summary"), groups)
    for endpoint in ("heating", "warm_water", "cold_water"):
        _collect_groups_from_consumption(payload.get(endpoint), groups)

    return sorted(groups)


def latest_readout_date_from_payloads(payloads: Iterable[Any]) -> date | None:
    """Return the latest readout date found across multiple payloads."""
    latest: date | None = None

    for payload in payloads:
        endpoint_latest = latest_readout_date_from_payload(payload)
        if endpoint_latest is not None and (latest is None or endpoint_latest > latest):
            latest = endpoint_latest

    return latest


def latest_readout_date_from_payload(payload: Any) -> date | None:
    """Return latest meter readout date from one endpoint payload."""
    detailed = _nested_get(payload, "data", "attributes", "calculation", "detailed")
    if not isinstance(detailed, Mapping):
        return None

    latest: date | None = None

    for room_data in detailed.values():
        if not isinstance(room_data, Mapping):
            continue
        for group_data in room_data.values():
            if not isinstance(group_data, Mapping):
                continue
            meters = group_data.get("meters")
            if not isinstance(meters, list):
                continue
            for meter in meters:
                if not isinstance(meter, Mapping):
                    continue
                parsed = _parse_iso_date(meter.get("last_readout_date"))
                if parsed is not None and (latest is None or parsed > latest):
                    latest = parsed

    return latest


def _collect_groups_from_summary(summary_payload: Any, groups: set[str]) -> None:
    calc = _nested_get(summary_payload, "data", "attributes", "calculation")
    if not isinstance(calc, Mapping):
        return

    for section in ("current", "real_estate_average", "benchmark"):
        _collect_group_keys(calc.get(section), groups)


def _collect_groups_from_consumption(consumption_payload: Any, groups: set[str]) -> None:
    calc = _nested_get(consumption_payload, "data", "attributes", "calculation")
    if not isinstance(calc, Mapping):
        return

    _collect_group_keys(calc.get("current"), groups)
    _collect_group_keys(_nested_get(calc, "estate_unit_totals", "current"), groups)

    month_by_month = calc.get("month_by_month")
    if isinstance(month_by_month, Mapping):
        for year_data in month_by_month.values():
            if not isinstance(year_data, Mapping):
                continue
            for month_data in year_data.values():
                _collect_group_keys(month_data, groups)

    real_estate_average = calc.get("real_estate_average")
    if isinstance(real_estate_average, Mapping):
        for year_key, year_data in real_estate_average.items():
            if year_key == "total" or not isinstance(year_data, Mapping):
                continue
            for month_data in year_data.values():
                _collect_group_keys(month_data, groups)

    detailed = calc.get("detailed")
    if isinstance(detailed, Mapping):
        for room_data in detailed.values():
            _collect_group_keys(room_data, groups)


def _collect_group_keys(container: Any, groups: set[str]) -> None:
    if not isinstance(container, Mapping):
        return
    for raw_key in container:
        group = _normalize_group(raw_key)
        if group:
            groups.add(group)


def _normalize_group(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip().lower()
    if text == "":
        return None
    return text


def _parse_iso_date(raw_value: Any) -> date | None:
    if not isinstance(raw_value, str):
        return None
    value = raw_value.strip()
    if len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
