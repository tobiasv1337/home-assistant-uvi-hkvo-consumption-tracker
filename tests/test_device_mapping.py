"""Tests for device topology mapping helpers."""

from __future__ import annotations

from custom_components.uvi.device_mapping import (
    build_root_device_context,
    derive_device_topology,
)
from custom_components.uvi.parser import build_flat_sensors
from tests.payload_samples import build_full_payload


def _context():
    payload = build_full_payload()
    return build_root_device_context(
        payload=payload,
        base_url="https://uvi.example.test",
        email="user@example.test",
        fallback_title="Fallback",
    )


def test_root_device_context_and_root_entity_mapping() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    context = _context()
    topology = derive_device_topology(
        context=context,
        attributes=sensors["estate_unit_area"]["attributes"],
    )

    assert context["root_name"] == "UVI 0018 (Berlin)"
    assert context["root_identifier"].endswith("_estate_241078")
    assert topology["identifier"] == context["root_identifier"]
    assert topology["via_identifier"] is None
    assert topology["name"] == context["root_name"]
    assert topology["model"] == "Tenant Portal"


def test_endpoint_entity_maps_to_child_device() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    context = _context()

    heating_topology = derive_device_topology(
        context=context,
        attributes=sensors["heating_current_month_h1_consumption"]["attributes"],
    )
    summary_topology = derive_device_topology(
        context=context,
        attributes=sensors["summary_current_h1_consumption"]["attributes"],
    )
    comparison_topology = derive_device_topology(
        context=context,
        attributes=sensors["comparison_w1_base_total"]["attributes"],
    )

    assert heating_topology["identifier"].endswith("_endpoint_heating")
    assert heating_topology["via_identifier"] == context["root_identifier"]
    assert heating_topology["name"] == "Heating"
    assert heating_topology["model"] == "Heating Overview"

    assert summary_topology["identifier"] == heating_topology["identifier"]
    assert summary_topology["via_identifier"] == context["root_identifier"]
    assert comparison_topology["identifier"].endswith("_endpoint_warm_water")
    assert comparison_topology["name"] == "Warm Water"


def test_meter_entity_maps_to_meter_device_with_room_name() -> None:
    payload = build_full_payload()
    sensors = build_flat_sensors(payload)

    context = _context()
    topology = derive_device_topology(
        context=context,
        attributes=sensors["meter_heat_1001_h1_consumption"]["attributes"],
    )

    assert topology["identifier"].endswith("_meter_heat_1001")
    assert topology["via_identifier"] == context["root_identifier"]
    assert topology["name"] == "Meter HEAT-1001 (Living)"
    assert topology["model"] == "Meter"


def test_meter_device_uses_meter_id_fallback_when_identifier_missing() -> None:
    context = _context()

    topology = derive_device_topology(
        context=context,
        attributes={
            "meter_id": 12345,
            "room_name": "Kitchen",
        },
    )

    assert topology["identifier"].endswith("_meter_12345")
    assert topology["name"] == "Meter 12345 (Kitchen)"
    assert topology["model"] == "Meter"
    assert topology["via_identifier"] == context["root_identifier"]


def test_summary_group_mapping_is_prefix_based_and_has_fallback() -> None:
    context = _context()

    heating_group_topology = derive_device_topology(
        context=context,
        attributes={
            "source_endpoint": "summary",
            "group": "H2",
        },
    )
    unknown_group_topology = derive_device_topology(
        context=context,
        attributes={
            "source_endpoint": "summary",
            "group": "X9",
        },
    )

    assert heating_group_topology["identifier"].endswith("_endpoint_heating")
    assert heating_group_topology["name"] == "Heating"
    assert unknown_group_topology["identifier"].endswith("_endpoint_group_x9")
    assert unknown_group_topology["name"] == "Group X9"
