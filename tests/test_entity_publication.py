"""High-level publication tests for flattened HA entities."""

from __future__ import annotations

import json
from typing import Any

import pytest

from custom_components.uvi.parser import build_flat_sensors
from tests.payload_samples import build_full_payload


def _is_verbose(pytestconfig) -> bool:
    return bool(getattr(pytestconfig, "uvi_verbose", False))


def _print_entity_report(sensors: dict[str, dict[str, Any]]) -> None:
    print("\n=== UVI Entity Publication Report ===")
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


def test_entities_cover_all_main_endpoints(pytestconfig) -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    if _is_verbose(pytestconfig):
        _print_entity_report(sensors)

    # Summary endpoint
    assert "summary_current_h1_consumption" in sensors
    assert "summary_current_w1_normalized_kwh" in sensors
    assert "summary_current_vs_building_average_h1_delta_percent" in sensors
    assert "summary_current_vs_average_tenant_h1_delta_percent" in sensors

    # Heating endpoint (current scope removed, only current_month remains)
    assert "heating_current_month_h1_consumption" in sensors
    assert "heating_estate_unit_totals_h1_consumption" in sensors
    assert "heating_current_month_h1_normalized_kwh" in sensors

    # Warm water endpoint (current scope removed)
    assert "warm_water_current_month_w1_consumption" in sensors

    # Cold water endpoint (current scope removed)
    assert "cold_water_current_month_k1_consumption" in sensors

    # Monthly comparison endpoint
    assert "comparison_h1_base_total" in sensors
    assert "comparison_k1_comparison_total" in sensors
    assert "comparison_w1_current_month_delta_percent" in sensors
    assert "comparison_h1_current_vs_previous_month_delta_percent" in sensors
    assert "comparison_h1_base_month_02" not in sensors
    assert any(
        item.get("month") == 2
        for item in sensors["comparison_h1_base_total"]["attributes"].get("series", [])
    )

    # Historical monthly comparison summary
    assert "comparison_h1_historical_entries_count" in sensors

    # Estate units endpoint
    assert "estate_units_count" in sensors
    assert "estate_unit_heated_area" in sensors
    assert "estate_unit_warm_water_area" in sensors
    assert "estate_unit_area" in sensors


def test_multiple_meters_publish_multiple_meter_entities_with_attributes() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    # Heating meters are exposed including cumulative readout totals.
    assert "meter_heat_1001_h1_consumption" in sensors
    assert "meter_heat_1001_h1_readout_total" in sensors
    assert sensors["meter_heat_1001_h1_readout_total"]["state_class"] == "total_increasing"
    assert sensors["meter_heat_1001_h1_readout_total"]["native_value"] == 90.0

    # Warm water has two meters in the sample payload.
    assert "meter_ww_2001_w1_consumption" in sensors
    assert "meter_ww_2002_w1_consumption" in sensors

    meter_1_attrs = sensors["meter_ww_2001_w1_consumption"]["attributes"]
    meter_2_attrs = sensors["meter_ww_2002_w1_consumption"]["attributes"]

    assert meter_1_attrs["meter_identifier"] == "WW-2001"
    assert meter_1_attrs["last_readout_date"] == "2026-02-28"
    assert meter_1_attrs["room_name"] == "Bath"

    assert meter_2_attrs["meter_identifier"] == "WW-2002"
    assert meter_2_attrs["last_readout_date"] == "2026-02-21"

    # Cold water has two meters too.
    assert "meter_cw_3001_k1_consumption" in sensors
    assert "meter_cw_3002_k1_consumption" in sensors

    # Readout totals are exposed as cumulative meter values.
    assert "meter_ww_2001_w1_readout_total" in sensors
    assert sensors["meter_ww_2001_w1_readout_total"]["state_class"] == "total_increasing"
    assert sensors["meter_ww_2001_w1_readout_total"]["native_value"] == 28.51

    # Per-meter kWh energy sensors are total_increasing for Energy Dashboard.
    heat_kwh = sensors["meter_heat_1001_h1_normalized_kwh"]
    assert heat_kwh["state_class"] == "total_increasing"
    assert heat_kwh["device_class"] == "energy"
    assert heat_kwh["native_unit"] == "kWh"
    assert heat_kwh["native_value"] == pytest.approx(282.31476, rel=1e-4)
    assert heat_kwh["attributes"]["room_name"] == "Living"

    ww_kwh = sensors["meter_ww_2001_w1_normalized_kwh"]
    assert ww_kwh["state_class"] == "total_increasing"
    assert ww_kwh["device_class"] == "energy"
    assert ww_kwh["native_unit"] == "kWh"

    # Cold water meters do not expose normalized_kwh.
    assert "meter_cw_3001_k1_normalized_kwh" not in sensors

    # Full meter metadata from detailed payload is preserved.
    heat_attrs = sensors["meter_heat_1001_h1_consumption"]["attributes"]
    assert heat_attrs["k_total_coefficient"] == 7.028
    assert heat_attrs["consumption_without_k_total_coefficient"] == 39.0
    assert heat_attrs["start_date"] == "2024-11-12 11:17:18 UTC"
    assert heat_attrs["status"] == "calculation"


def test_endpoint_readout_totals_are_total_increasing() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    assert "heating_meters_h1_readout_total" in sensors
    assert sensors["heating_meters_h1_readout_total"]["state_class"] == "total_increasing"
    assert sensors["heating_meters_h1_readout_total"]["native_value"] == 228.0
    assert sensors["heating_meters_h1_readout_total"]["attributes"]["meter_count"] == 2

    assert "warm_water_meters_w1_readout_total" in sensors
    assert sensors["warm_water_meters_w1_readout_total"]["native_value"] == pytest.approx(39.01)

    assert "cold_water_meters_k1_readout_total" in sensors
    assert sensors["cold_water_meters_k1_readout_total"]["native_value"] == pytest.approx(97.308)


def test_energy_totals_for_energy_dashboard() -> None:
    """Aggregated kWh sensors (total_increasing + device_class energy) for the HA Energy Dashboard."""
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    # Heating energy total (sum of normalized_kwh_consumption across all h1 meters)
    h1_energy = sensors["heating_meters_h1_energy_total"]
    assert h1_energy["state_class"] == "total_increasing"
    assert h1_energy["device_class"] == "energy"
    assert h1_energy["native_unit"] == "kWh"
    assert h1_energy["native_value"] == pytest.approx(473.30354, rel=1e-4)
    assert h1_energy["attributes"]["meter_count"] == 2

    # Warm water energy total (sum of normalized_kwh_consumption across all w1 meters)
    w1_energy = sensors["warm_water_meters_w1_energy_total"]
    assert w1_energy["state_class"] == "total_increasing"
    assert w1_energy["device_class"] == "energy"
    assert w1_energy["native_unit"] == "kWh"
    assert w1_energy["native_value"] == pytest.approx(142.8164, rel=1e-4)
    assert w1_energy["attributes"]["meter_count"] == 2

    # Cold water should NOT have an energy total (no normalized_kwh_consumption)
    assert "cold_water_meters_k1_energy_total" not in sensors


def test_entity_units_and_device_classes_are_mapped_correctly() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    heat = sensors["heating_current_month_h1_consumption"]
    warm = sensors["warm_water_current_month_w1_consumption"]
    cold = sensors["cold_water_current_month_k1_consumption"]
    heated_area = sensors["estate_unit_heated_area"]

    assert heat["native_unit"] == "HKV"
    assert heat["device_class"] is None

    # measurement sensors don't get device_class (HA restriction);
    # only total/total_increasing sensors carry water/energy device_class.
    assert warm["native_unit"] == "m3"
    assert warm["device_class"] is None  # measurement → no device_class

    assert cold["native_unit"] == "m3"
    assert cold["device_class"] is None  # measurement → no device_class

    assert heated_area["native_unit"] == "m2"
    assert heated_area["device_class"] is None

    # total_increasing sensors DO keep device_class
    warm_readout = sensors["warm_water_meters_w1_readout_total"]
    assert warm_readout["device_class"] == "water"
    assert warm_readout["state_class"] == "total_increasing"

    warm_energy = sensors["warm_water_meters_w1_energy_total"]
    assert warm_energy["device_class"] == "energy"
    assert warm_energy["state_class"] == "total_increasing"


def test_entity_publication_report_structure() -> None:
    """Ensure enough entities are being published for representative payloads."""
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    assert len(sensors) > 20


def test_high_volume_info_sensors_are_disabled_by_default() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    assert sensors["summary_current_h1_consumption"]["enabled_default"] is True
    assert sensors["comparison_h1_base_total"]["enabled_default"] is False
    assert sensors["comparison_h1_current_month_delta_percent"]["enabled_default"] is True
    assert sensors["comparison_h1_base_total"]["entity_category"] == "diagnostic"
    assert sensors["estate_units_count"]["enabled_default"] is False
