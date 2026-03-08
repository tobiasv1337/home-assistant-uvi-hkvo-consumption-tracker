"""DataUpdateCoordinator for UVI."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import UviApiClient, UviAuthenticationError, UviRequestError
from .const import (
    DEFAULT_MONTHLY_COMPARISON_GROUPS,
    DOMAIN,
    HISTORY_BACKFILL_MAX_YEARS,
)
from .fetch_strategy import (
    billing_period_window,
    candidate_month_windows,
    candidate_window_days,
    discover_monthly_comparison_groups,
    latest_readout_date_from_payload,
    window_dates,
)
from .parser import build_flat_sensors

_LOGGER = logging.getLogger(__name__)


class UviDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches UVI API data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        api: UviApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=update_interval,
        )
        self.entry = entry
        self.api = api
        self._historical_monthly_cache: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all available endpoint data."""
        try:
            await self.api.authenticate()
        except UviAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Authentication to UVI portal failed"
            ) from err
        except UviRequestError as err:
            raise UpdateFailed(err.message) from err

        now = dt_util.now()
        today = now.date()

        base_year = now.year
        comparison_year = now.year - 1

        payload: dict[str, Any] = {
            "fetched_at": now.isoformat(),
            "window": {
                "base_year": base_year,
                "comparison_year": comparison_year,
            },
            "monthly_comparison": {},
        }

        base_tasks: dict[str, Awaitable[Any]] = {
            "user": self.api.fetch_user(),
            "estate_units": self.api.fetch_estate_units(),
        }

        await _run_task_batch_or_raise(
            tasks=base_tasks,
            required={"user", "estate_units"},
            payload=payload,
        )

        consumption_payload, window_meta = await self._async_fetch_consumption_for_best_window(
            today=today,
        )
        payload.update(consumption_payload)
        payload["window"].update(window_meta)

        summary_payload, summary_meta = await self._async_fetch_summary_for_best_month_window(
            today=today,
        )
        if summary_payload is not None:
            payload["summary"] = summary_payload
        payload["window"]["summary"] = summary_meta

        discovered_groups = discover_monthly_comparison_groups(payload)
        if not discovered_groups:
            discovered_groups = list(DEFAULT_MONTHLY_COMPARISON_GROUPS)

        payload["discovered_monthly_comparison_groups"] = discovered_groups

        comparison_tasks: dict[str, Awaitable[Any]] = {
            group: self.api.fetch_monthly_comparison(
                group=group,
                base_year=base_year,
                comparison_year=comparison_year,
            )
            for group in discovered_groups
        }

        comparison_results = await _run_task_batch(
            tasks=comparison_tasks,
            required=set(),
        )

        for group, result in comparison_results.items():
            if isinstance(result, Exception):
                continue
            payload["monthly_comparison"][group] = result

        await self._async_ensure_historical_backfill(
            groups=discovered_groups,
            base_year=base_year,
        )
        payload["historical_monthly_comparison"] = self._historical_monthly_cache

        payload["flat_sensors"] = build_flat_sensors(payload, reference_date=today)
        return payload

    async def _async_ensure_historical_backfill(
        self,
        groups: list[str],
        base_year: int,
    ) -> None:
        """Backfill historical monthly-comparison data once per group.

        A hard backend error keeps `loaded=False` so future refreshes can retry.
        """
        for group in groups:
            group_key = group.lower()
            cached = self._historical_monthly_cache.get(group_key)
            if isinstance(cached, Mapping) and bool(cached.get("loaded")):
                continue

            history = {
                "loaded": False,
                "base-year": {},
                "comparison-year": {},
                "comparison-year-climate-corrected": {},
            }
            years_without_data = 0
            hard_failure = False

            for offset in range(HISTORY_BACKFILL_MAX_YEARS):
                fetch_base_year = base_year - offset
                fetch_comparison_year = fetch_base_year - 1

                try:
                    response = await self.api.fetch_monthly_comparison(
                        group=group_key,
                        base_year=fetch_base_year,
                        comparison_year=fetch_comparison_year,
                    )
                except UviAuthenticationError as err:
                    raise ConfigEntryAuthFailed(
                        "Authentication to UVI portal failed"
                    ) from err
                except UviRequestError as err:
                    if err.status in {404, 422}:
                        years_without_data += 1
                        if years_without_data >= 2:
                            break
                        continue
                    _LOGGER.warning(
                        "Historical backfill failed for group %s (%s): %s",
                        group_key,
                        err.status,
                        err.message,
                    )
                    hard_failure = True
                    break

                had_data = _merge_historical_monthly_comparison(
                    history=history,
                    payload=response,
                )
                if had_data:
                    years_without_data = 0
                else:
                    years_without_data += 1

                if years_without_data >= 2:
                    break

            history["loaded"] = not hard_failure
            self._historical_monthly_cache[group_key] = history

    async def _async_fetch_consumption_for_best_window(
        self,
        today: date,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch each consumption endpoint with its own adaptive window."""
        endpoints = (
            ("heating", self.api.fetch_heating),
            ("warm_water", self.api.fetch_warm_water),
            ("cold_water", self.api.fetch_cold_water),
        )

        payload: dict[str, Any] = {}
        endpoint_meta: dict[str, Any] = {}

        for endpoint_name, fetcher in endpoints:
            endpoint_payload, meta = await self._async_fetch_single_consumption_endpoint(
                endpoint_name=endpoint_name,
                fetcher=fetcher,
                today=today,
            )
            endpoint_meta[endpoint_name] = meta
            if endpoint_payload is not None:
                payload[endpoint_name] = endpoint_payload

        return payload, {"consumption": endpoint_meta}

    async def _async_fetch_single_consumption_endpoint(
        self,
        endpoint_name: str,
        fetcher: Callable[[str, str], Awaitable[dict[str, Any]]],
        today: date,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Fetch one consumption endpoint with adaptive + month windows."""
        attempts: list[dict[str, Any]] = []

        window_candidates: list[tuple[date, date, int, str]] = []
        seen_windows: set[tuple[str, str]] = set()

        for days in candidate_window_days(today):
            from_date, to_date = window_dates(today=today, days=days)
            key = (from_date.isoformat(), to_date.isoformat())
            if key in seen_windows:
                continue
            seen_windows.add(key)
            window_candidates.append((from_date, to_date, days, f"adaptive_{days}d"))

        for from_iso, to_iso, label in candidate_month_windows(today):
            from_date = date.fromisoformat(from_iso)
            to_date = date.fromisoformat(to_iso)
            key = (from_iso, to_iso)
            if key in seen_windows:
                continue
            seen_windows.add(key)
            window_candidates.append(
                (
                    from_date,
                    to_date,
                    (to_date - from_date).days + 1,
                    label,
                )
            )

        # Add full billing-period window as final fallback to cover the
        # typical 12-month HKVO period for complete per-meter consumption.
        bp_from_iso, bp_to_iso, bp_label = billing_period_window(today)
        bp_key = (bp_from_iso, bp_to_iso)
        if bp_key not in seen_windows:
            seen_windows.add(bp_key)
            bp_from_date = date.fromisoformat(bp_from_iso)
            bp_to_date = date.fromisoformat(bp_to_iso)
            window_candidates.append(
                (
                    bp_from_date,
                    bp_to_date,
                    (bp_to_date - bp_from_date).days + 1,
                    bp_label,
                )
            )

        best_success_payload: dict[str, Any] | None = None
        best_success_attempt: dict[str, Any] | None = None
        best_latest_readout: date | None = None
        best_span_days = -1

        for from_date, to_date, days, label in window_candidates:
            from_iso = from_date.isoformat()
            to_iso = to_date.isoformat()

            results = await _run_task_batch(
                tasks={endpoint_name: fetcher(from_iso, to_iso)},
                required=set(),
            )
            result = results.get(endpoint_name)

            if isinstance(result, Exception):
                status = result.status if isinstance(result, UviRequestError) else None
                attempts.append(
                    {
                        "from": from_iso,
                        "to": to_iso,
                        "days": days,
                        "window": label,
                        "status": status,
                        "result": "no_data" if status in {404, 422} else "error",
                    }
                )
                continue

            latest_readout = latest_readout_date_from_payload(result)
            selected = {
                "from": from_iso,
                "to": to_iso,
                "days": days,
                "window": label,
                "status": 200,
                "result": "success",
                "latest_readout_date": latest_readout.isoformat() if latest_readout else None,
            }
            attempts.append(selected)

            # Best case: endpoint has at least one readout inside this window.
            if latest_readout is not None and latest_readout >= from_date:
                selected["selection_reason"] = "latest_readout_within_window"
                return result, {"selected_window": selected, "attempts": attempts}

            should_update_best = (
                best_success_payload is None
                or (latest_readout is not None and best_latest_readout is None)
                or (
                    latest_readout is not None
                    and best_latest_readout is not None
                    and latest_readout > best_latest_readout
                )
                or (latest_readout == best_latest_readout and days > best_span_days)
                or (
                    latest_readout is None
                    and best_latest_readout is None
                    and days > best_span_days
                )
            )

            if should_update_best:
                best_success_payload = result
                best_success_attempt = selected
                best_latest_readout = latest_readout
                best_span_days = days

        if best_success_payload is not None and best_success_attempt is not None:
            selected = dict(best_success_attempt)
            selected["selection_reason"] = "fallback_best_success"
            return best_success_payload, {"selected_window": selected, "attempts": attempts}

        return None, {"selected_window": None, "attempts": attempts}

    async def _async_fetch_summary_for_best_month_window(
        self,
        today: date,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Fetch summary with billing-period window first, then month fallbacks."""
        attempts: list[dict[str, Any]] = []

        # Try full billing period first (covers typical 12-month HKVO period),
        # then fall back to smaller month windows.
        bp_from, bp_to, bp_label = billing_period_window(today)
        windows = [(bp_from, bp_to, bp_label)] + candidate_month_windows(today)

        for from_iso, to_iso, label in windows:
            results = await _run_task_batch(
                tasks={"summary": self.api.fetch_summary(from_iso, to_iso)},
                required=set(),
            )
            result = results.get("summary")

            if isinstance(result, Exception):
                status = result.status if isinstance(result, UviRequestError) else None
                attempts.append(
                    {
                        "from": from_iso,
                        "to": to_iso,
                        "window": label,
                        "status": status,
                        "result": (
                            "no_data"
                            if status in {404, 422}
                            else "error"
                        ),
                    }
                )
                continue

            selected = {
                "from": from_iso,
                "to": to_iso,
                "window": label,
                "status": 200,
                "result": "success",
            }
            attempts.append(selected)
            return result, {"selected_window": selected, "attempts": attempts}

        return None, {"selected_window": None, "attempts": attempts}


async def _run_task_batch_or_raise(
    tasks: Mapping[str, Awaitable[Any]],
    required: set[str],
    payload: dict[str, Any],
) -> None:
    """Run concurrent tasks and write successful results into payload."""
    results = await _run_task_batch(tasks=tasks, required=required)
    for name, result in results.items():
        if isinstance(result, Exception):
            continue
        payload[name] = result


async def _run_task_batch(
    tasks: Mapping[str, Awaitable[Any]],
    required: set[str],
) -> dict[str, Any]:
    """Run concurrent tasks and map each result by name."""
    names = list(tasks.keys())
    coroutines = [tasks[name] for name in names]

    try:
        results = await asyncio.gather(*coroutines, return_exceptions=True)
    except UviAuthenticationError as err:
        raise ConfigEntryAuthFailed(
            "Authentication to UVI portal failed"
        ) from err
    except UviRequestError as err:
        raise UpdateFailed(err.message) from err

    mapped: dict[str, Any] = {}

    for name, result in zip(names, results, strict=True):
        mapped[name] = result

        if isinstance(result, UviAuthenticationError):
            raise ConfigEntryAuthFailed(
                "Authentication to UVI portal failed"
            ) from result

        if isinstance(result, Exception):
            if isinstance(result, UviRequestError):
                if result.status in {404, 422}:
                    _LOGGER.warning(
                        "Endpoint %s not available (%s). Skipping.",
                        name,
                        result.status,
                    )
                else:
                    _LOGGER.warning("Endpoint %s failed: %s", name, result.message)
            else:
                _LOGGER.warning("Endpoint %s failed: %s", name, result)

            if name in required:
                raise UpdateFailed(f"Required endpoint failed: {name}")

    return mapped


def _merge_historical_monthly_comparison(
    history: dict[str, Any],
    payload: Any,
) -> bool:
    """Merge one monthly-comparison response into the historical cache."""
    attributes = _nested_get(payload, "data", "attributes")
    if not isinstance(attributes, Mapping):
        return False

    had_data = False
    for section in (
        "base-year",
        "comparison-year",
        "comparison-year-climate-corrected",
    ):
        section_data = attributes.get(section)
        year = _to_int(_nested_get(section_data, "year"))
        if year is None:
            continue

        consumptions = _copy_consumptions_section(section_data)
        if consumptions:
            had_data = True

        section_store = history.setdefault(section, {})
        section_store[str(year)] = consumptions

    return had_data


def _copy_consumptions_section(section_data: Any) -> list[dict[str, Any]]:
    if not isinstance(section_data, Mapping):
        return []

    items = section_data.get("consumptions")
    if not isinstance(items, list):
        return []

    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            result.append(dict(item))
    return result


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
