"""Optional online tests against a real UVI portal."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from typing import Any
from urllib.parse import urlparse

import pytest

from custom_components.uvi.api import (
    UviApiClient,
    UviAuthenticationError,
    UviRequestError,
)
from custom_components.uvi.const import DEFAULT_MONTHLY_COMPARISON_GROUPS
from custom_components.uvi.device_mapping import (
    build_root_device_context,
    derive_device_topology,
)
from custom_components.uvi.fetch_strategy import (
    candidate_month_windows,
    candidate_window_days,
    discover_monthly_comparison_groups,
    latest_readout_date_from_payload,
    window_dates,
)
from custom_components.uvi.parser import build_flat_sensors

pytestmark = pytest.mark.online

EXPECTED_NO_DATA_STATUSES = {404, 422}


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    pytest.skip(f"Missing env var: {name}")


def _is_verbose(pytestconfig) -> bool:
    return bool(getattr(pytestconfig, "uvi_verbose", False))


def _online_config() -> dict[str, str]:
    base_url = _required_env("UVI_BASE_URL").rstrip("/")
    email = _required_env("UVI_EMAIL")
    password = _required_env("UVI_PASSWORD")

    if not urlparse(base_url).scheme:
        pytest.skip("UVI_BASE_URL must include scheme (https://...)")

    return {
        "base_url": base_url,
        "email": email,
        "password": password,
    }


def _is_unreachable_network_error(err: Exception) -> bool:
    text = str(err).lower()
    indicators = (
        "cannot connect to host",
        "nodename nor servname provided",
        "name or service not known",
        "temporary failure in name resolution",
    )
    return any(indicator in text for indicator in indicators)


def _candidate_consumption_windows(today: date) -> list[tuple[str, str, str]]:
    windows: list[tuple[str, str, str]] = []
    for days in candidate_window_days(today):
        from_date, to_date = window_dates(today=today, days=days)
        windows.append((from_date.isoformat(), to_date.isoformat(), f"adaptive_{days}d"))

    windows.extend(candidate_month_windows(today))
    return _dedupe_windows(windows)


def _candidate_comparison_year_pairs(today: date) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for offset in range(4):
        base_year = today.year - offset
        pairs.append((base_year, base_year - 1))
    return pairs


def _dedupe_windows(windows: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str, str]] = []
    for from_date, to_date, label in windows:
        key = (from_date, to_date)
        if key in seen:
            continue
        seen.add(key)
        result.append((from_date, to_date, label))
    return result


def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _normalize_group(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip().lower()
    if not value:
        return None
    return value


def _endpoint_has_calculation(payload: Any) -> bool:
    calc = _nested_get(payload, "data", "attributes", "calculation")
    return isinstance(calc, Mapping)


def _endpoint_has_meter_data(payload: Any) -> bool:
    detailed = _nested_get(payload, "data", "attributes", "calculation", "detailed")
    if not isinstance(detailed, Mapping):
        return False

    for room_data in detailed.values():
        if not isinstance(room_data, Mapping):
            continue
        for group_data in room_data.values():
            if not isinstance(group_data, Mapping):
                continue
            meters = group_data.get("meters")
            if isinstance(meters, list) and len(meters) > 0:
                return True
    return False


def _has_source_endpoint_sensor(
    sensors: Mapping[str, Mapping[str, Any]],
    source_endpoint: str,
) -> bool:
    for descriptor in sensors.values():
        attrs = descriptor.get("attributes")
        if not isinstance(attrs, Mapping):
            continue
        if attrs.get("source_endpoint") == source_endpoint:
            return True
    return False


def _has_meter_sensor_for_endpoint(
    sensors: Mapping[str, Mapping[str, Any]],
    endpoint_name: str,
) -> bool:
    for key, descriptor in sensors.items():
        if not key.startswith("meter_"):
            continue
        attrs = descriptor.get("attributes")
        if not isinstance(attrs, Mapping):
            continue
        if attrs.get("source_endpoint") == endpoint_name:
            return True
    return False


def _print_entity_report(
    sensors: Mapping[str, Mapping[str, Any]],
    *,
    device_context: Mapping[str, str] | None = None,
) -> None:
    print("\n=== UVI Online Entity Publication Report ===")
    print(f"Entity count: {len(sensors)}")
    for key in sorted(sensors):
        descriptor = sensors[key]
        print(f"\n- entity_key: {key}")
        print(f"  name: {descriptor.get('name')}")
        print(f"  native_value: {descriptor.get('native_value')}")
        print(f"  native_unit: {descriptor.get('native_unit')}")
        print(f"  device_class: {descriptor.get('device_class')}")
        print(f"  state_class: {descriptor.get('state_class')}")
        print("  attributes:")
        attrs = descriptor.get("attributes") or {}
        print(json.dumps(attrs, indent=2, sort_keys=True, ensure_ascii=True))

    if device_context is not None:
        _print_entities_grouped_by_device(sensors, device_context)


def _print_entities_grouped_by_device(
    sensors: Mapping[str, Mapping[str, Any]],
    device_context: Mapping[str, str],
) -> None:
    grouped: dict[str, dict[str, Any]] = {}

    for key in sorted(sensors):
        descriptor = sensors[key]
        raw_attrs = descriptor.get("attributes")
        attrs = raw_attrs if isinstance(raw_attrs, Mapping) else None
        topology = derive_device_topology(context=device_context, attributes=attrs)
        device_identifier = str(topology["identifier"])

        group = grouped.setdefault(
            device_identifier,
            {
                "name": str(topology["name"]),
                "model": str(topology["model"]),
                "via_identifier": topology["via_identifier"],
                "entities": [],
            },
        )
        group["entities"].append(key)

    print("\n=== UVI Online Device Entity Grouping ===")
    print(f"Device count: {len(grouped)}")
    for device_identifier, group in sorted(
        grouped.items(),
        key=lambda item: _device_sort_key(item[0], item[1]),
    ):
        print(f"\n- device_identifier: {device_identifier}")
        print(f"  name: {group['name']}")
        print(f"  model: {group['model']}")
        print(f"  via_identifier: {group['via_identifier']}")
        print(f"  entity_count: {len(group['entities'])}")
        print("  entities:")
        for entity_key in group["entities"]:
            print(f"    - {entity_key}")


def _device_sort_key(
    device_identifier: str,
    device_data: Mapping[str, Any],
) -> tuple[int, str]:
    if device_data.get("via_identifier") is None:
        return (0, device_identifier)
    if "_endpoint_" in device_identifier:
        return (1, device_identifier)
    return (2, device_identifier)


async def _fetch_json_with_windows(
    endpoint_name: str,
    fetcher: Callable[[str, str], Awaitable[dict[str, Any]]],
    windows: list[tuple[str, str, str]],
    verbose: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    last_success: tuple[dict[str, Any], dict[str, Any]] | None = None

    for from_date, to_date, label in windows:
        try:
            payload = await fetcher(from_date, to_date)
        except UviRequestError as err:
            if err.status in EXPECTED_NO_DATA_STATUSES:
                attempts.append(
                    {
                        "from": from_date,
                        "to": to_date,
                        "window": label,
                        "status": err.status,
                        "result": "no_data",
                    }
                )
                if verbose:
                    print(
                        f"{endpoint_name} no-data status {err.status} for window "
                        f"{from_date} {to_date} ({label})"
                    )
                continue
            raise
        else:
            latest_readout = latest_readout_date_from_payload(payload)
            attempt = {
                "from": from_date,
                "to": to_date,
                "window": label,
                "status": 200,
                "result": "success",
                "latest_readout_date": (
                    latest_readout.isoformat() if latest_readout else None
                ),
            }
            attempts.append(attempt)
            last_success = (payload, attempt)
            if verbose:
                print(
                    f"{endpoint_name} window success: {from_date} {to_date} "
                    f"({label}), latest_readout={latest_readout}"
                )

            # Prefer windows that contain a readout date in the queried span.
            if latest_readout is not None and latest_readout.isoformat() >= from_date:
                attempt["selection_reason"] = "latest_readout_within_window"
                return payload, {"selected_window": attempt, "attempts": attempts}

    if last_success is not None:
        payload, selected = last_success
        selected["selection_reason"] = "fallback_last_success"
        return payload, {"selected_window": selected, "attempts": attempts}

    return None, {"selected_window": None, "attempts": attempts}


async def _fetch_monthly_comparison_for_group(
    client: UviApiClient,
    group: str,
    year_pairs: list[tuple[int, int]],
    verbose: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []

    for base_year, comparison_year in year_pairs:
        try:
            payload = await client.fetch_monthly_comparison(
                group=group,
                base_year=base_year,
                comparison_year=comparison_year,
            )
        except UviRequestError as err:
            if err.status in EXPECTED_NO_DATA_STATUSES:
                attempts.append(
                    {
                        "group": group,
                        "base_year": base_year,
                        "comparison_year": comparison_year,
                        "status": err.status,
                        "result": "no_data",
                    }
                )
                if verbose:
                    print(
                        f"monthly-comparison {group} no-data status {err.status} for "
                        f"base={base_year} comparison={comparison_year}"
                    )
                continue
            raise
        else:
            attempts.append(
                {
                    "group": group,
                    "base_year": base_year,
                    "comparison_year": comparison_year,
                    "status": 200,
                    "result": "success",
                }
            )
            if verbose:
                print(
                    f"monthly-comparison {group} success: "
                    f"base={base_year} comparison={comparison_year}"
                )
            return payload, {"selected_years": attempts[-1], "attempts": attempts}

    return None, {"selected_years": None, "attempts": attempts}


@pytest.fixture(scope="module")
def online_bundle(pytestconfig):
    config = _online_config()
    aiohttp = pytest.importorskip("aiohttp")
    verbose = _is_verbose(pytestconfig)

    async def _run() -> dict[str, Any]:
        today = date.today()
        summary_windows = candidate_month_windows(today)
        consumption_windows = _candidate_consumption_windows(today)
        comparison_year_pairs = _candidate_comparison_year_pairs(today)

        async with aiohttp.ClientSession() as session:
            client = UviApiClient(
                session=session,
                base_url=config["base_url"],
                email=config["email"],
                password=config["password"],
            )

            user_payload = await client.fetch_user()
            estate_units_payload = await client.fetch_estate_units()

            summary_payload, summary_meta = await _fetch_json_with_windows(
                endpoint_name="summary",
                fetcher=client.fetch_summary,
                windows=summary_windows,
                verbose=verbose,
            )

            consumption_payloads: dict[str, dict[str, Any]] = {}
            consumption_meta: dict[str, Any] = {}
            for endpoint_name, fetcher in (
                ("heating", client.fetch_heating),
                ("warm_water", client.fetch_warm_water),
                ("cold_water", client.fetch_cold_water),
            ):
                payload, meta = await _fetch_json_with_windows(
                    endpoint_name=endpoint_name,
                    fetcher=fetcher,
                    windows=consumption_windows,
                    verbose=verbose,
                )
                consumption_meta[endpoint_name] = meta
                if payload is not None:
                    consumption_payloads[endpoint_name] = payload

            discovered_groups = discover_monthly_comparison_groups(
                {
                    "summary": summary_payload,
                    **consumption_payloads,
                }
            )
            groups_to_query = (
                discovered_groups
                if discovered_groups
                else list(DEFAULT_MONTHLY_COMPARISON_GROUPS)
            )

            monthly_comparison_payloads: dict[str, dict[str, Any]] = {}
            monthly_comparison_meta: dict[str, Any] = {}
            for group in groups_to_query:
                payload, meta = await _fetch_monthly_comparison_for_group(
                    client=client,
                    group=group,
                    year_pairs=comparison_year_pairs,
                    verbose=verbose,
                )
                monthly_comparison_meta[group] = meta
                if payload is not None:
                    monthly_comparison_payloads[group] = payload

            parser_payload: dict[str, Any] = {
                "user": user_payload,
                "estate_units": estate_units_payload,
                "monthly_comparison": monthly_comparison_payloads,
            }
            if summary_payload is not None:
                parser_payload["summary"] = summary_payload
            parser_payload.update(consumption_payloads)

            flat_sensors = build_flat_sensors(parser_payload)
            device_context = build_root_device_context(
                payload=parser_payload,
                base_url=config["base_url"],
                email=config["email"],
                fallback_title="UVI",
            )

            return {
                "today": today.isoformat(),
                "user": user_payload,
                "estate_units": estate_units_payload,
                "summary": summary_payload,
                "summary_meta": summary_meta,
                "consumption": consumption_payloads,
                "consumption_meta": consumption_meta,
                "discovered_groups": discovered_groups,
                "queried_groups": groups_to_query,
                "monthly_comparison": monthly_comparison_payloads,
                "monthly_comparison_meta": monthly_comparison_meta,
                "parser_payload": parser_payload,
                "flat_sensors": flat_sensors,
                "device_context": device_context,
            }

    try:
        return asyncio.run(_run())
    except UviAuthenticationError as err:
        if _is_unreachable_network_error(err):
            pytest.skip(f"Online portal not reachable from test environment: {err}")
        raise


def test_online_login_and_fetch_user(pytestconfig) -> None:
    config = _online_config()
    aiohttp = pytest.importorskip("aiohttp")
    verbose = _is_verbose(pytestconfig)

    async def _run() -> None:
        async with aiohttp.ClientSession() as session:
            client = UviApiClient(
                session=session,
                base_url=config["base_url"],
                email=config["email"],
                password=config["password"],
            )

            user_payload = await client.fetch_user()
            assert user_payload.get("data", {}).get("id")
            if verbose:
                print(
                    "online login ok, user_id:",
                    user_payload.get("data", {}).get("id"),
                )

    try:
        asyncio.run(_run())
    except UviAuthenticationError as err:
        if _is_unreachable_network_error(err):
            pytest.skip(f"Online portal not reachable from test environment: {err}")
        raise


def test_online_fetches_consumption_endpoints_with_adaptive_windows(online_bundle) -> None:
    consumption_payloads = online_bundle["consumption"]
    if not consumption_payloads:
        pytest.skip(
            "No consumption payload was available for any endpoint in tested windows. "
            f"Metadata: {online_bundle['consumption_meta']}"
        )

    for endpoint_name, payload in consumption_payloads.items():
        assert isinstance(payload, Mapping), f"{endpoint_name} payload must be mapping"
        assert "data" in payload, f"{endpoint_name} payload should include data object"
        assert _endpoint_has_calculation(payload), (
            f"{endpoint_name} payload did not include calculation section"
        )


def test_online_fetches_monthly_comparison_for_dynamic_groups(online_bundle) -> None:
    comparison_payloads = online_bundle["monthly_comparison"]
    if not comparison_payloads:
        pytest.skip(
            "Monthly comparison returned no payload for queried groups. "
            f"Metadata: {online_bundle['monthly_comparison_meta']}"
        )

    for group, payload in comparison_payloads.items():
        attributes = _nested_get(payload, "data", "attributes")
        assert isinstance(attributes, Mapping), f"monthly comparison {group} missing attributes"

        response_group = _normalize_group(attributes.get("group"))
        assert response_group == group.lower()

        base_consumptions = _nested_get(attributes, "base-year", "consumptions")
        assert isinstance(base_consumptions, list)


def test_online_builds_flat_sensors_from_real_payloads(
    online_bundle,
    pytestconfig,
) -> None:
    sensors = online_bundle["flat_sensors"]
    assert isinstance(sensors, Mapping)
    assert len(sensors) > 0
    assert "estate_units_count" in sensors

    if getattr(pytestconfig, "uvi_verbose", False):
        print("\n=== UVI Online Endpoint Meta ===")
        print(json.dumps(online_bundle["summary_meta"], indent=2, sort_keys=True))
        print(json.dumps(online_bundle["consumption_meta"], indent=2, sort_keys=True))
        print(json.dumps(online_bundle["monthly_comparison_meta"], indent=2, sort_keys=True))
        _print_entity_report(sensors, device_context=online_bundle["device_context"])

    summary_payload = online_bundle["summary"]
    if summary_payload is not None and _endpoint_has_calculation(summary_payload):
        assert _has_source_endpoint_sensor(sensors, "summary")

    for endpoint_name, payload in online_bundle["consumption"].items():
        if _endpoint_has_calculation(payload):
            assert _has_source_endpoint_sensor(sensors, endpoint_name)
        if _endpoint_has_meter_data(payload):
            assert _has_meter_sensor_for_endpoint(sensors, endpoint_name), (
                f"{endpoint_name} payload has meter data but no meter_* sensors were built"
            )

    for group in online_bundle["monthly_comparison"]:
        prefix = f"comparison_{group.lower()}_"
        assert any(key.startswith(prefix) for key in sensors), (
            f"No comparison sensors found for group {group}"
        )
