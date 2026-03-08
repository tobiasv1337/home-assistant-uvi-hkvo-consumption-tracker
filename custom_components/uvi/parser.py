"""Payload normalization and sensor extraction for UVI."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date as dt_date
from typing import Any

from .const import GROUP_METADATA

_MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _month_label(month: int) -> str:
    """Return abbreviated month name (1-based)."""
    if 1 <= month <= 12:
        return _MONTH_ABBR[month]
    return str(month)


def _months_range_label(series: list[dict]) -> str:
    """Return e.g. 'Jan\u2013Feb' from a comparison series."""
    months = sorted(int(item.get("month", 0)) for item in series if isinstance(item, dict))
    months = [m for m in months if 1 <= m <= 12]
    if not months:
        return ""
    if len(months) == 1:
        return _month_label(months[0])
    return f"{_month_label(months[0])}\u2013{_month_label(months[-1])}"


def build_flat_sensors(
    payload: Mapping[str, Any],
    reference_date: dt_date | None = None,
) -> dict[str, dict[str, Any]]:
    """Flatten endpoint payloads into a stable sensor dictionary."""
    sensors: dict[str, dict[str, Any]] = {}
    group_units = _build_group_unit_map(payload)
    consumption_window_meta = _nested_get(payload, "window", "consumption")

    _parse_estate_unit_area_sensors(sensors, payload)
    summary_window_meta = _nested_get(payload, "window", "summary")
    _parse_summary(sensors, payload.get("summary"), group_units, summary_window_meta)
    _parse_consumption_endpoint(
        sensors,
        "heating",
        payload.get("heating"),
        group_units,
        _nested_get(consumption_window_meta, "heating"),
    )
    _parse_consumption_endpoint(
        sensors,
        "warm_water",
        payload.get("warm_water"),
        group_units,
        _nested_get(consumption_window_meta, "warm_water"),
    )
    _parse_consumption_endpoint(
        sensors,
        "cold_water",
        payload.get("cold_water"),
        group_units,
        _nested_get(consumption_window_meta, "cold_water"),
    )

    monthly_comparison = payload.get("monthly_comparison") or {}
    if isinstance(monthly_comparison, Mapping):
        for group, group_payload in monthly_comparison.items():
            _parse_monthly_comparison(
                sensors, group, group_payload, reference_date=reference_date,
            )

    _parse_historical_monthly_comparison(
        sensors,
        payload.get("historical_monthly_comparison"),
    )

    estate_units = _as_list(_nested_get(payload.get("estate_units"), "data"))
    _add_sensor(
        sensors,
        key="estate_units_count",
        name="Estate Units Count",
        native_value=len(estate_units),
        icon="mdi:home-city",
        state_class="measurement",
        attributes={
            "estate_unit_ids": [item.get("id") for item in estate_units if isinstance(item, Mapping)],
            "description": "Number of estate units (apartments) linked to your account.",
        },
    )

    _apply_sensor_presentation_defaults(sensors)
    return sensors


def _parse_summary(
    sensors: dict[str, dict[str, Any]],
    summary_payload: Any,
    group_units: Mapping[str, str],
    window_meta: Any = None,
) -> None:
    calc = _nested_get(summary_payload, "data", "attributes", "calculation")
    if not isinstance(calc, Mapping):
        return
    window_attributes = _window_attributes(window_meta)
    period_label = _period_label_from_window(window_meta)

    section_labels = {
        "current": "Billing Period",
        "real_estate_average": "Building Avg (Period)",
        "benchmark": "All-Buildings Benchmark",
    }
    section_descriptions = {
        "current": (
            "Your total {group} consumption for the current billing period (year to date)."
        ),
        "real_estate_average": (
            "Average {group} consumption across all units in your building"
            " for the same billing period."
        ),
        "benchmark": (
            "Reference value from the all-buildings portfolio benchmark"
            " for {group} (across all properties and users)."
        ),
    }

    for section in ("current", "real_estate_average", "benchmark"):
        section_data = calc.get(section)
        if not isinstance(section_data, Mapping):
            continue

        section_label = section_labels.get(section, section.replace("_", " ").title())

        for group, values in section_data.items():
            if not isinstance(values, Mapping):
                continue
            group_key = group.lower()
            meta = GROUP_METADATA.get(group_key, {})
            group_label = meta.get("label") or group.upper()
            raw_unit = _resolve_raw_unit(group_key, group_units)
            raw_device_class = _device_class_for_unit(raw_unit)

            consumption = _to_float(values.get("consumption"))
            if consumption is not None:
                _add_sensor(
                    sensors,
                    key=f"summary_{section}_{group.lower()}_consumption",
                    name=f"{group_label} {section_label}",
                    native_value=consumption,
                    native_unit=raw_unit,
                    icon=meta.get("icon"),
                    state_class="measurement",
                    device_class=raw_device_class,
                    suggested_display_precision=3,
                    attributes={
                        "section": section,
                        "group": group.upper(),
                        "status": values.get("status"),
                        "period_label": period_label,
                        "source_endpoint": "summary",
                        "description": section_descriptions.get(section, "").format(group=group_label.lower()),
                        **window_attributes,
                    },
                )

            normalized = _to_float(values.get("normalized_kwh_consumption"))
            if normalized is not None:
                _add_sensor(
                    sensors,
                    key=f"summary_{section}_{group.lower()}_normalized_kwh",
                    name=f"{group_label} {section_label} Energy",
                    native_value=normalized,
                    native_unit="kWh",
                    icon="mdi:flash",
                    device_class="energy",
                    state_class="measurement",
                    suggested_display_precision=3,
                    attributes={
                        "section": section,
                        "group": group.upper(),
                        "status": values.get("status"),
                        "period_label": period_label,
                        "source_endpoint": "summary",
                        "description": (
                            section_descriptions.get(section, "").format(group=group_label.lower())
                            + " (kWh estimate)"
                        ),
                        **window_attributes,
                    },
                )

    _add_summary_relative_comparison_sensors(
        sensors=sensors,
        calc=calc,
        group_units=group_units,
        window_meta=window_meta,
    )


def _add_summary_relative_comparison_sensors(
    sensors: dict[str, dict[str, Any]],
    calc: Mapping[str, Any],
    group_units: Mapping[str, str],
    window_meta: Any = None,
) -> None:
    """Add summary comparisons vs building average and average tenant."""
    current = calc.get("current")
    if not isinstance(current, Mapping):
        return
    window_attributes = _window_attributes(window_meta)
    period_label = _period_label_from_window(window_meta)

    reference_specs = (
        ("real_estate_average", "building_average", "Building (Period)"),
        ("benchmark", "average_tenant", "All-Buildings Benchmark"),
    )

    reference_descriptions = {
        "real_estate_average": (
            "Your billing-period {group} consumption compared to the average of all units"
            " in your building for the same period. Positive = above average."
        ),
        "benchmark": (
            "Your billing-period {group} consumption compared to the all-buildings"
            " portfolio benchmark. Positive = above benchmark."
        ),
    }

    for group, current_values in current.items():
        if not isinstance(current_values, Mapping):
            continue
        current_consumption = _to_float(current_values.get("consumption"))
        if current_consumption is None:
            continue

        group_key = str(group).lower()
        group_meta = GROUP_METADATA.get(group_key, {})
        group_label = group_meta.get("label") or str(group).upper()
        raw_unit = _resolve_raw_unit(group_key, group_units)
        raw_device_class = _device_class_for_unit(raw_unit)

        for section_key, reference_key, reference_label in reference_specs:
            section = calc.get(section_key)
            if not isinstance(section, Mapping):
                continue
            reference_values = section.get(group)
            if not isinstance(reference_values, Mapping):
                continue
            reference_consumption = _to_float(reference_values.get("consumption"))
            if reference_consumption is None:
                continue

            delta_absolute = current_consumption - reference_consumption
            desc = reference_descriptions.get(section_key, "").format(group=group_label.lower())
            _add_sensor(
                sensors=sensors,
                key=f"summary_current_vs_{reference_key}_{group_key}_delta_absolute",
                name=f"{group_label} vs {reference_label} Diff",
                native_value=delta_absolute,
                native_unit=raw_unit,
                icon=group_meta.get("icon"),
                device_class=raw_device_class,
                state_class="measurement",
                suggested_display_precision=3,
                attributes={
                    "group": str(group).upper(),
                    "reference_section": section_key,
                    "current_consumption": current_consumption,
                    "reference_consumption": reference_consumption,
                    "period_label": period_label,
                    "source_endpoint": "summary",
                    "description": f"Absolute difference. {desc}",
                    **window_attributes,
                },
            )

            if reference_consumption == 0:
                continue
            _add_sensor(
                sensors=sensors,
                key=f"summary_current_vs_{reference_key}_{group_key}_delta_percent",
                name=f"{group_label} vs {reference_label}",
                native_value=(delta_absolute / reference_consumption) * 100,
                native_unit="%",
                icon="mdi:percent",
                state_class="measurement",
                suggested_display_precision=2,
                attributes={
                    "group": str(group).upper(),
                    "reference_section": section_key,
                    "current_consumption": current_consumption,
                    "reference_consumption": reference_consumption,
                    "period_label": period_label,
                    "source_endpoint": "summary",
                    "description": desc,
                    **window_attributes,
                },
            )


def _parse_consumption_endpoint(
    sensors: dict[str, dict[str, Any]],
    endpoint_name: str,
    endpoint_payload: Any,
    group_units: Mapping[str, str],
    window_meta: Any = None,
) -> None:
    calc = _nested_get(endpoint_payload, "data", "attributes", "calculation")
    if not isinstance(calc, Mapping):
        return
    window_attributes = _window_attributes(window_meta)

    # NOTE: The ``current`` section is intentionally skipped.  Its values
    # duplicate the latest ``month_by_month`` entry in practice (the adaptive
    # window almost always resolves to a single month) and the duplicate
    # sensors confuse users.  Year-to-date totals are provided by the
    # *summary* endpoint instead.

    totals = _nested_get(calc, "estate_unit_totals", "current")
    if isinstance(totals, Mapping):
        for group, values in totals.items():
            if not isinstance(values, Mapping):
                continue
            _add_group_value_sensor(
                sensors=sensors,
                endpoint_name=endpoint_name,
                group=group,
                values=values,
                group_units=group_units,
                scope="estate_unit_totals",
                source_endpoint=endpoint_name,
                window_attributes=window_attributes,
            )

    month_by_month = calc.get("month_by_month")
    if isinstance(month_by_month, Mapping):
        flattened = _flatten_month_by_month(month_by_month)
        for group in _groups_in_month_series(flattened):
            latest = _latest_month_item(flattened, group)
            if latest is None:
                continue
            year, month, values = latest
            _add_group_value_sensor(
                sensors=sensors,
                endpoint_name=endpoint_name,
                group=group,
                values=values,
                group_units=group_units,
                scope="current_month",
                source_endpoint=endpoint_name,
                window_attributes=window_attributes,
                extra_attributes={
                    "year": year,
                    "month": month,
                    "history": _series_for_group(flattened, group),
                },
            )

    # NOTE: Previous-month values and month-over-month deltas are intentionally
    # omitted here.  The *monthly-comparison* endpoint provides the same data
    # with richer context (incomplete-month flags, year-over-year comparison,
    # climate correction) and is the single source-of-truth for comparison
    # sensors.  Keeping duplicates from the consumption endpoints caused
    # confusing overlaps.

    # Collect groups the user actually has data for so we skip ghost groups
    # (e.g. H2 delivered by the API but absent from the tenant's own meters).
    own_groups: set[str] = set()
    current_section = calc.get("current")
    if isinstance(current_section, Mapping):
        own_groups.update(current_section.keys())
    if isinstance(month_by_month, Mapping):
        for _mv in _flatten_month_by_month(month_by_month).values():
            own_groups.update(_mv.keys())

    real_estate_average = calc.get("real_estate_average")
    if isinstance(real_estate_average, Mapping):
        flattened_average = _flatten_real_estate_average(real_estate_average)
        for group in _groups_in_month_series(flattened_average):
            if own_groups and group not in own_groups:
                continue  # skip groups the tenant doesn't use
            latest = _latest_month_item(flattened_average, group)
            if latest is None:
                continue
            year, month, values = latest
            _add_group_value_sensor(
                sensors=sensors,
                endpoint_name=endpoint_name,
                group=group,
                values=values,
                group_units=group_units,
                scope="real_estate_average_latest",
                source_endpoint=endpoint_name,
                window_attributes=window_attributes,
                extra_attributes={
                    "year": year,
                    "month": month,
                    "history": _series_for_group(flattened_average, group),
                },
            )

    detailed = calc.get("detailed")
    if isinstance(detailed, Mapping):
        _add_endpoint_meter_readout_totals(
            sensors=sensors,
            endpoint_name=endpoint_name,
            detailed=detailed,
            group_units=group_units,
            window_attributes=window_attributes,
        )
        for room_id, room_values in detailed.items():
            if not isinstance(room_values, Mapping):
                continue
            for group, group_data in room_values.items():
                if not isinstance(group_data, Mapping):
                    continue
                room_name = group_data.get("name")
                meters = _as_list(group_data.get("meters"))
                for meter in meters:
                    if not isinstance(meter, Mapping):
                        continue
                    meter_id = meter.get("id")
                    identifier = meter.get("identifier")
                    meter_key = _meter_entity_key_component(meter)
                    if meter_key is None:
                        continue
                    key_base = f"meter_{meter_key}_{group.lower()}"
                    group_key = group.lower()
                    group_meta = GROUP_METADATA.get(group_key, {})
                    raw_unit = _resolve_raw_unit(
                        group_key, group_units, endpoint_name=endpoint_name
                    )
                    raw_device_class = _device_class_for_unit(raw_unit)

                    raw_value = _to_float(meter.get("consumption"))
                    if raw_value is not None:
                        _add_sensor(
                            sensors,
                            key=f"{key_base}_consumption",
                            name=f"{identifier or meter_id} Consumption",
                            native_value=raw_value,
                            native_unit=raw_unit,
                            icon=group_meta.get("icon"),
                            device_class=raw_device_class,
                            state_class="measurement",
                            suggested_display_precision=3,
                            attributes={
                                "meter_id": meter_id,
                                "meter_identifier": identifier,
                                "room_id": room_id,
                                "room_name": room_name,
                                "group": group.upper(),
                                "last_readout_date": meter.get("last_readout_date"),
                                "first_readout_value": _to_float(meter.get("first_readout_value")),
                                "last_readout_value": _to_float(meter.get("last_readout_value")),
                                "k_total_coefficient": _to_float(meter.get("k_total_coefficient")),
                                "consumption_without_k_total_coefficient": _to_float(
                                    meter.get("consumption_without_k_total_coefficient")
                                ),
                                "status": meter.get("status"),
                                "start_date": meter.get("start_date"),
                                "end_date": meter.get("end_date"),
                                "source_endpoint": endpoint_name,
                                "description": (
                                    f"Period consumption for meter {identifier or meter_id}"
                                    f" in {room_name or 'unknown room'}."
                                ),
                                **window_attributes,
                            },
                        )

                    last_readout_value = _to_float(meter.get("last_readout_value"))
                    if last_readout_value is not None:
                        _add_sensor(
                            sensors,
                            key=f"{key_base}_readout_total",
                            name=f"{identifier or meter_id} Meter Reading",
                            native_value=last_readout_value,
                            native_unit=raw_unit,
                            icon=group_meta.get("icon"),
                            device_class=raw_device_class,
                            state_class="total_increasing",
                            suggested_display_precision=3,
                            attributes={
                                "meter_id": meter_id,
                                "meter_identifier": identifier,
                                "room_id": room_id,
                                "room_name": room_name,
                                "group": group.upper(),
                                "last_readout_date": meter.get("last_readout_date"),
                                "first_readout_value": _to_float(meter.get("first_readout_value")),
                                "last_readout_value": _to_float(meter.get("last_readout_value")),
                                "k_total_coefficient": _to_float(meter.get("k_total_coefficient")),
                                "consumption_without_k_total_coefficient": _to_float(
                                    meter.get("consumption_without_k_total_coefficient")
                                ),
                                "status": meter.get("status"),
                                "start_date": meter.get("start_date"),
                                "end_date": meter.get("end_date"),
                                "source_endpoint": endpoint_name,
                                "description": (
                                    f"Latest absolute meter reading for {identifier or meter_id}."
                                    " Cumulative value that only increases."
                                ),
                                **window_attributes,
                            },
                        )

                    normalized = _to_float(meter.get("normalized_kwh_consumption"))
                    if normalized is not None:
                        _add_sensor(
                            sensors,
                            key=f"{key_base}_normalized_kwh",
                            name=f"{identifier or meter_id} Energy",
                            native_value=normalized,
                            native_unit="kWh",
                            icon="mdi:flash",
                            device_class="energy",
                            state_class="total_increasing",
                            suggested_display_precision=3,
                            attributes={
                                "meter_id": meter_id,
                                "meter_identifier": identifier,
                                "room_id": room_id,
                                "room_name": room_name,
                                "group": group.upper(),
                                "last_readout_date": meter.get("last_readout_date"),
                                "consumption_without_k_total_coefficient": _to_float(
                                    meter.get("consumption_without_k_total_coefficient")
                                ),
                                "status": meter.get("status"),
                                "start_date": meter.get("start_date"),
                                "end_date": meter.get("end_date"),
                                "source_endpoint": endpoint_name,
                                "description": (
                                    f"Estimated energy consumption for meter {identifier or meter_id}"
                                    f" in {room_name or 'unknown room'} (kWh normalization)."
                                ),
                                **window_attributes,
                            },
                        )


def _parse_monthly_comparison(
    sensors: dict[str, dict[str, Any]],
    group: str,
    comparison_payload: Any,
    reference_date: dt_date | None = None,
) -> None:
    attributes = _nested_get(comparison_payload, "data", "attributes")
    if not isinstance(attributes, Mapping):
        return

    group_code = str(attributes.get("group", group)).lower()
    group_meta = GROUP_METADATA.get(group_code, {})
    group_label = group_meta.get("label") or group_code.upper()

    base_year_data = attributes.get("base-year")
    comparison_year_data = attributes.get("comparison-year")
    corrected_data = attributes.get("comparison-year-climate-corrected")

    base_series = _comparison_series(base_year_data)
    comparison_series_full = _comparison_series(comparison_year_data)
    corrected_series_full = _comparison_series(corrected_data)

    if not base_series:
        return

    # The API may deliver all 12 months for the comparison year while the
    # base year only covers e.g. Jan-Feb.  For a fair year-over-year
    # comparison we must restrict the comparison/corrected series to the
    # same months present in the base year.
    base_months = {int(item["month"]) for item in base_series}
    comparison_series = [item for item in comparison_series_full if int(item["month"]) in base_months]
    corrected_series = [item for item in corrected_series_full if int(item["month"]) in base_months]

    unit = _normalize_unit(base_series[0].get("unit"))
    device_class = _device_class_for_unit(unit)

    base_total = _sum_quantities(base_series)
    comparison_total = _sum_quantities(comparison_series)
    corrected_total = _sum_quantities(corrected_series)

    base_year = _year_value(base_year_data)
    comparison_year = _year_value(comparison_year_data)

    base_range = _months_range_label(base_series)
    comp_range = _months_range_label(comparison_series)

    if base_total is not None:
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_base_total",
            name=f"{group_label} This Year to Date",
            native_value=base_total,
            native_unit=unit,
            device_class=device_class,
            icon=group_meta.get("icon"),
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "base_year": base_year,
                "period_label": f"{base_range} {base_year}" if base_range and base_year else None,
                "months_included": len(base_series),
                "series": base_series,
                "source_endpoint": "monthly-comparison",
                "description": f"Your cumulative {group_label.lower()} consumption for {base_range} {base_year}.",
            },
        )

    if comparison_total is not None:
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_comparison_total",
            name=f"{group_label} Last Year Same Period",
            native_value=comparison_total,
            native_unit=unit,
            device_class=device_class,
            icon=group_meta.get("icon"),
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "comparison_year": _year_value(comparison_year_data),
                "period_label": f"{comp_range} {comparison_year}" if comp_range and comparison_year else None,
                "months_included": len(comparison_series),
                "series": comparison_series,
                "source_endpoint": "monthly-comparison",
                "description": (
                    f"Your {group_label.lower()} consumption for the same months"
                    f" ({comp_range}) in {comparison_year}."
                ),
            },
        )

    if corrected_total is not None:
        corrected_range = _months_range_label(corrected_series)
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_comparison_total_climate_corrected",
            name=f"{group_label} Last Year Same Period Climate Adj.",
            native_value=corrected_total,
            native_unit=unit,
            device_class=device_class,
            icon=group_meta.get("icon"),
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "comparison_year": _year_value(corrected_data),
                "period_label": (
                    f"{corrected_range} {comparison_year}"
                    if corrected_range and comparison_year
                    else None
                ),
                "months_included": len(corrected_series),
                "series": corrected_series,
                "source_endpoint": "monthly-comparison",
                "description": (
                    f"Climate-adjusted {group_label.lower()} consumption"
                    f" for {corrected_range} {comparison_year}."
                ),
            },
        )

    if base_total is not None and comparison_total not in (None, 0):
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_delta_percent_total",
            name=f"{group_label} Year over Year (Same Period)",
            native_value=((base_total - comparison_total) / comparison_total) * 100,
            native_unit="%",
            icon="mdi:percent",
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "base_year": base_year,
                "comparison_year": comparison_year,
                "period_label": f"{base_range} {base_year} vs {comp_range} {comparison_year}" if base_range else None,
                "source_endpoint": "monthly-comparison",
                "description": (
                    f"Year-over-year % change comparing your {base_range} {base_year}"
                    f" consumption to {comp_range} {comparison_year}."
                    " Positive = higher this year."
                ),
            },
        )

    # Use the latest *complete* month for comparisons.  The API may include a
    # partial current-calendar-month; comparing it with a full prior month
    # would be misleading.
    latest_base = _latest_complete_comparison_item(
        base_series, base_year=base_year, reference_date=reference_date,
    )
    if not latest_base:
        return

    month = int(latest_base["month"])
    base_value = _to_float(latest_base.get("quantity"))
    comparison_value = _comparison_value_for_month(comparison_series, month)
    previous_base = _previous_comparison_item(base_series, month)

    # NOTE: ``comparison_*_current_month_base`` and
    # ``comparison_*_previous_month_base`` sensors have been removed.  Their
    # values duplicated the endpoint ``current_month`` sensors and the
    # per-month data is available in the ``series`` attribute of the yearly
    # total sensor.

    # Month-over-month comparison (e.g. Feb vs Jan of the same year)
    if previous_base is not None:
        previous_month = int(previous_base["month"])
        previous_value = _to_float(previous_base.get("quantity"))
        mom_label = f"{_month_label(previous_month)}\u2192{_month_label(month)} {base_year}"

        if base_value is not None and previous_value not in (None, 0):
            _add_sensor(
                sensors=sensors,
                key=f"comparison_{group_code}_current_vs_previous_month_delta_percent",
                name=f"{group_label} Month over Month",
                native_value=((base_value - previous_value) / previous_value) * 100,
                native_unit="%",
                icon="mdi:percent",
                state_class="measurement",
                suggested_display_precision=2,
                attributes={
                    "group": group_code.upper(),
                    "base_year": base_year,
                    "current_month": month,
                    "previous_month": previous_month,
                    "current_value": base_value,
                    "previous_value": previous_value,
                    "period_label": mom_label,
                    "source_endpoint": "monthly-comparison",
                    "description": (
                        f"% change from {_month_label(previous_month)}"
                        f" to {_month_label(month)} {base_year}. Positive = increase."
                    ),
                },
            )

        if base_value is not None and previous_value is not None:
            _add_sensor(
                sensors=sensors,
                key=f"comparison_{group_code}_current_vs_previous_month_delta_absolute",
                name=f"{group_label} Month over Month Diff",
                native_value=base_value - previous_value,
                native_unit=unit,
                device_class=device_class,
                icon=group_meta.get("icon"),
                state_class="measurement",
                suggested_display_precision=2,
                attributes={
                    "group": group_code.upper(),
                    "base_year": base_year,
                    "current_month": month,
                    "previous_month": previous_month,
                    "current_value": base_value,
                    "previous_value": previous_value,
                    "period_label": mom_label,
                    "source_endpoint": "monthly-comparison",
                    "description": (
                        f"Absolute difference from {_month_label(previous_month)}"
                        f" to {_month_label(month)} {base_year}."
                    ),
                },
            )

    # Same-month year-over-year (e.g. Feb 2026 vs Feb 2025)
    month_name = _month_label(month)
    if comparison_value is not None:
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_current_month_comparison",
            name=f"{group_label} Same Month Last Year",
            native_value=comparison_value,
            native_unit=unit,
            device_class=device_class,
            icon=group_meta.get("icon"),
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "month": month,
                "comparison_year": _year_value(comparison_year_data),
                "period_label": f"{month_name} {comparison_year}",
                "source_endpoint": "monthly-comparison",
                "description": f"Your {group_label.lower()} consumption in {month_name} {comparison_year}.",
            },
        )

    if base_value is not None and comparison_value not in (None, 0):
        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_current_month_delta_percent",
            name=f"{group_label} vs Same Month Last Year",
            native_value=((base_value - comparison_value) / comparison_value) * 100,
            native_unit="%",
            icon="mdi:percent",
            state_class="measurement",
            suggested_display_precision=2,
            attributes={
                "group": group_code.upper(),
                "month": month,
                "base_year": base_year,
                "comparison_year": comparison_year,
                "period_label": f"{month_name} {base_year} vs {month_name} {comparison_year}",
                "source_endpoint": "monthly-comparison",
                "description": (
                    f"% change: {month_name} {base_year} vs {month_name} {comparison_year}."
                    " Positive = higher this year."
                ),
            },
        )


def _parse_historical_monthly_comparison(
    sensors: dict[str, dict[str, Any]],
    historical_payload: Any,
) -> None:
    if not isinstance(historical_payload, Mapping):
        return

    for raw_group, history in historical_payload.items():
        if not isinstance(history, Mapping):
            continue

        group_code = str(raw_group).lower()
        group_meta = GROUP_METADATA.get(group_code, {})
        group_label = group_meta.get("label") or group_code.upper()

        section_years: dict[str, list[int]] = {}
        years_available: set[int] = set()
        entries_count = 0

        for section_name in (
            "base-year",
            "comparison-year",
            "comparison-year-climate-corrected",
        ):
            section_data = history.get(section_name)
            if not isinstance(section_data, Mapping):
                continue

            years: set[int] = set()
            for raw_year, consumptions in section_data.items():
                year = _to_int(raw_year)
                if year is None:
                    continue
                years.add(year)
                years_available.add(year)

                if isinstance(consumptions, list):
                    entries_count += len(consumptions)

            if years:
                section_years[section_name] = sorted(years)

        if not years_available and entries_count == 0:
            continue

        _add_sensor(
            sensors,
            key=f"comparison_{group_code}_historical_entries_count",
            name=f"{group_label} Historical Data Points",
            native_value=entries_count,
            icon=group_meta.get("icon"),
            state_class="measurement",
            attributes={
                "group": group_code.upper(),
                "loaded": bool(history.get("loaded")),
                "years_available": sorted(years_available),
                "sections_available": section_years,
                "history": dict(history),
                "source_endpoint": "monthly-comparison-historical",
                "description": f"Number of historical monthly data points available for {group_label.lower()}.",
            },
        )


def _add_group_value_sensor(
    sensors: dict[str, dict[str, Any]],
    endpoint_name: str,
    group: str,
    values: Mapping[str, Any],
    group_units: Mapping[str, str],
    scope: str,
    source_endpoint: str,
    window_attributes: Mapping[str, Any] | None = None,
    extra_attributes: Mapping[str, Any] | None = None,
) -> None:
    group_key = group.lower()
    meta = GROUP_METADATA.get(group_key, {})
    group_label = meta.get("label") or group.upper()

    scope_labels = {
        "current_month": "Latest Month",
        "estate_unit_totals": "Unit Total (Period)",
        "real_estate_average_latest": "Building Avg (Latest Month)",
    }
    scope_descriptions = {
        "current_month": "Your {group} consumption for the latest month with data.",
        "estate_unit_totals": (
            "Total {group} consumption for your unit in the current billing period."
        ),
        "real_estate_average_latest": (
            "Average {group} consumption across all units in your building"
            " for the latest month."
        ),
    }
    scope_label = scope_labels.get(scope, scope.replace("_", " ").title())
    scope_desc = scope_descriptions.get(scope, "").format(group=group_label.lower())

    raw_unit = _resolve_raw_unit(group_key, group_units, endpoint_name=endpoint_name)
    raw_device_class = _device_class_for_unit(raw_unit)

    raw_value = _to_float(values.get("consumption"))
    if raw_value is not None:
        attributes: dict[str, Any] = {
            "group": group.upper(),
            "scope": scope,
            "status": values.get("status"),
            "source_endpoint": source_endpoint,
        }
        if extra_attributes:
            attributes.update(extra_attributes)
        if window_attributes:
            attributes.update(window_attributes)
        # Add period label from extra_attributes year/month if available
        year = attributes.get("year")
        month = attributes.get("month")
        if year and month:
            attributes["period_label"] = f"{_month_label(int(month))} {year}"
        if scope_desc:
            attributes["description"] = scope_desc

        _add_sensor(
            sensors,
            key=f"{endpoint_name}_{scope}_{group_key}_consumption",
            name=f"{group_label} {scope_label}",
            native_value=raw_value,
            native_unit=raw_unit,
            icon=meta.get("icon"),
            device_class=raw_device_class,
            state_class="measurement",
            suggested_display_precision=3,
            attributes=attributes,
        )

    normalized = _to_float(values.get("normalized_kwh_consumption"))
    if normalized is not None:
        attributes = {
            "group": group.upper(),
            "scope": scope,
            "status": values.get("status"),
            "source_endpoint": source_endpoint,
        }
        if extra_attributes:
            attributes.update(extra_attributes)
        if window_attributes:
            attributes.update(window_attributes)
        year = attributes.get("year")
        month = attributes.get("month")
        if year and month:
            attributes["period_label"] = f"{_month_label(int(month))} {year}"
        if scope_desc:
            attributes["description"] = f"{scope_desc} (kWh estimate)"

        _add_sensor(
            sensors,
            key=f"{endpoint_name}_{scope}_{group_key}_normalized_kwh",
            name=f"{group_label} {scope_label} Energy",
            native_value=normalized,
            native_unit="kWh",
            icon="mdi:flash",
            device_class="energy",
            state_class="measurement",
            suggested_display_precision=3,
            attributes=attributes,
        )


def _flatten_month_by_month(month_by_month: Mapping[str, Any]) -> dict[tuple[int, int], Mapping[str, Any]]:
    flattened: dict[tuple[int, int], Mapping[str, Any]] = {}
    for year_key, months in month_by_month.items():
        if not isinstance(months, Mapping):
            continue
        year = _to_int(year_key)
        if year is None:
            continue
        for month_key, month_values in months.items():
            if not isinstance(month_values, Mapping):
                continue
            month = _to_int(month_key)
            if month is None:
                continue
            flattened[(year, month)] = month_values
    return flattened


def _flatten_real_estate_average(real_estate_average: Mapping[str, Any]) -> dict[tuple[int, int], Mapping[str, Any]]:
    flattened: dict[tuple[int, int], Mapping[str, Any]] = {}
    for year_key, months in real_estate_average.items():
        if year_key == "total" or not isinstance(months, Mapping):
            continue
        year = _to_int(year_key)
        if year is None:
            continue
        for month_key, month_values in months.items():
            if not isinstance(month_values, Mapping):
                continue
            month = _to_int(month_key)
            if month is None:
                continue
            normalized_month_values: dict[str, Any] = {}
            for group, value in month_values.items():
                if isinstance(value, Mapping):
                    normalized_month_values[group] = value
                else:
                    normalized_month_values[group] = {"consumption": value}
            flattened[(year, month)] = normalized_month_values
    return flattened


def _groups_in_month_series(flattened: Mapping[tuple[int, int], Mapping[str, Any]]) -> set[str]:
    groups: set[str] = set()
    for month_values in flattened.values():
        for group in month_values:
            groups.add(str(group))
    return groups


def _latest_month_item(
    flattened: Mapping[tuple[int, int], Mapping[str, Any]],
    group: str,
) -> tuple[int, int, Mapping[str, Any]] | None:
    for year, month in sorted(flattened.keys(), reverse=True):
        values = flattened[(year, month)].get(group)
        if isinstance(values, Mapping):
            return (year, month, values)
    return None


def _previous_month_item(
    flattened: Mapping[tuple[int, int], Mapping[str, Any]],
    group: str,
    latest_year: int,
    latest_month: int,
) -> tuple[int, int, Mapping[str, Any]] | None:
    keys = sorted(flattened.keys(), reverse=True)
    for year, month in keys:
        if (year, month) >= (latest_year, latest_month):
            continue
        values = flattened[(year, month)].get(group)
        if isinstance(values, Mapping):
            return (year, month, values)
    return None


def _series_for_group(
    flattened: Mapping[tuple[int, int], Mapping[str, Any]],
    group: str,
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for year, month in sorted(flattened.keys()):
        values = flattened[(year, month)].get(group)
        if not isinstance(values, Mapping):
            continue
        series.append(
            {
                "year": year,
                "month": month,
                "consumption": _to_float(values.get("consumption")),
                "normalized_kwh_consumption": _to_float(
                    values.get("normalized_kwh_consumption")
                ),
                "status": values.get("status"),
            }
        )
    return series


def _comparison_series(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, Mapping):
        return []
    items = _as_list(data.get("consumptions"))
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        month = _to_int(item.get("month"))
        quantity = _to_float(item.get("quantity"))
        if month is None or quantity is None:
            continue
        result.append(
            {
                "month": month,
                "quantity": quantity,
                "unit": item.get("unit"),
                "incomplete": item.get("incomplete", False),
            }
        )
    return sorted(result, key=lambda it: int(it["month"]))


def _sum_quantities(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None
    return float(sum(float(item["quantity"]) for item in items))


def _latest_comparison_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=lambda item: int(item["month"]))


def _latest_complete_comparison_item(
    items: list[dict[str, Any]],
    base_year: int | None = None,
    reference_date: dt_date | None = None,
) -> dict[str, Any] | None:
    """Return the latest comparison item that represents a complete month.

    Skips months explicitly flagged as ``incomplete`` and – when a
    *reference_date* is supplied – also skips the current calendar month
    of the base year because it is still accumulating data.  Comparing a
    partial current month with a full prior month would be misleading.
    """
    for item in sorted(items, key=lambda x: -int(x["month"])):
        if item.get("incomplete", False):
            continue
        if (
            reference_date is not None
            and base_year is not None
            and base_year == reference_date.year
            and int(item["month"]) == reference_date.month
        ):
            continue
        return item
    return None


def _comparison_value_for_month(items: list[dict[str, Any]], month: int) -> float | None:
    for item in items:
        if int(item["month"]) == month:
            return float(item["quantity"])
    return None


def _previous_comparison_item(
    items: list[dict[str, Any]],
    month: int,
) -> dict[str, Any] | None:
    candidates = [item for item in items if int(item["month"]) < month]
    if not candidates:
        return None
    return max(candidates, key=lambda item: int(item["month"]))


def _year_value(data: Any) -> int | None:
    if not isinstance(data, Mapping):
        return None
    return _to_int(data.get("year"))


def _build_group_unit_map(payload: Mapping[str, Any]) -> dict[str, str]:
    """Build best-effort unit mapping per group."""
    units: dict[str, str] = {}

    for group_key, group_meta in GROUP_METADATA.items():
        unit = _normalize_unit(group_meta.get("raw_unit"))
        if unit:
            units[group_key.lower()] = unit

    monthly_comparison = payload.get("monthly_comparison")
    if not isinstance(monthly_comparison, Mapping):
        return units

    for raw_group_key, comparison_payload in monthly_comparison.items():
        group_key = str(raw_group_key).lower()
        attributes = _nested_get(comparison_payload, "data", "attributes")
        if not isinstance(attributes, Mapping):
            continue

        unit = _extract_unit_from_comparison_section(attributes.get("base-year"))
        if unit is None:
            unit = _extract_unit_from_comparison_section(attributes.get("comparison-year"))
        if unit is None:
            unit = _extract_unit_from_comparison_section(
                attributes.get("comparison-year-climate-corrected")
            )
        if unit:
            units[group_key] = unit

    return units


def _extract_unit_from_comparison_section(section_data: Any) -> str | None:
    if not isinstance(section_data, Mapping):
        return None
    for item in _as_list(section_data.get("consumptions")):
        if not isinstance(item, Mapping):
            continue
        unit = _normalize_unit(item.get("unit"))
        if unit:
            return unit
    return None


def _resolve_raw_unit(
    group_key: str,
    group_units: Mapping[str, str],
    endpoint_name: str | None = None,
) -> str | None:
    unit = group_units.get(group_key.lower())
    if unit is not None:
        return unit

    if endpoint_name in {"warm_water", "cold_water"}:
        return "m3"
    if endpoint_name == "heating":
        return "HKV"
    return None


def _parse_estate_unit_area_sensors(
    sensors: dict[str, dict[str, Any]],
    payload: Mapping[str, Any],
) -> None:
    """Parse area-related sensors from estate-unit metadata."""
    estate_unit = None
    for endpoint in ("summary", "heating", "warm_water", "cold_water"):
        candidate = _nested_get(payload.get(endpoint), "data", "attributes", "estate-unit")
        if isinstance(candidate, Mapping):
            estate_unit = candidate
            break

    if not isinstance(estate_unit, Mapping):
        return

    area_specs = (
        ("heated_area", "Heated Area", "mdi:ruler-square", "Total heated area of your estate unit."),
        ("warm_water_area", "Warm Water Area", "mdi:water-thermometer", "Area used for warm-water cost allocation."),
        ("area", "Estate Unit Area", "mdi:floor-plan", "Total area of your estate unit."),
    )

    for field_name, title, icon, desc in area_specs:
        value = _to_float(estate_unit.get(field_name))
        if value is None:
            continue
        _add_sensor(
            sensors=sensors,
            key=f"estate_unit_{field_name}",
            name=title,
            native_value=value,
            native_unit="m2",
            icon=icon,
            state_class="measurement",
            attributes={
                "estate_unit_id": estate_unit.get("id"),
                "source_field": field_name,
                "description": desc,
            },
        )


def _add_endpoint_meter_readout_totals(
    sensors: dict[str, dict[str, Any]],
    endpoint_name: str,
    detailed: Mapping[str, Any],
    group_units: Mapping[str, str],
    window_attributes: Mapping[str, Any] | None = None,
) -> None:
    """Add aggregated readout-total sensors per endpoint/group for Energy use-cases."""
    by_group: dict[str, dict[str, Any]] = {}

    for room_values in detailed.values():
        if not isinstance(room_values, Mapping):
            continue
        for group, group_data in room_values.items():
            if not isinstance(group_data, Mapping):
                continue
            meters = _as_list(group_data.get("meters"))
            group_key = str(group).lower()
            accumulator = by_group.setdefault(
                group_key,
                {
                    "total": 0.0,
                    "total_kwh": 0.0,
                    "meter_count": 0,
                    "meter_count_kwh": 0,
                    "identifiers": [],
                    "latest_readout_date": None,
                },
            )

            for meter in meters:
                if not isinstance(meter, Mapping):
                    continue

                readout = _to_float(meter.get("last_readout_value"))
                if readout is not None:
                    accumulator["total"] += readout
                    accumulator["meter_count"] += 1

                normalized_kwh = _to_float(meter.get("normalized_kwh_consumption"))
                if normalized_kwh is not None:
                    accumulator["total_kwh"] += normalized_kwh
                    accumulator["meter_count_kwh"] += 1

                identifier = meter.get("identifier")
                if identifier is not None and readout is not None:
                    accumulator["identifiers"].append(str(identifier))

                latest = _latest_date_string(
                    accumulator.get("latest_readout_date"),
                    meter.get("last_readout_date"),
                )
                accumulator["latest_readout_date"] = latest

    for group_key, acc in by_group.items():
        meta = GROUP_METADATA.get(group_key, {})
        group_label = meta.get("label") or group_key.upper()
        unit = _resolve_raw_unit(group_key, group_units, endpoint_name=endpoint_name)
        device_class = _device_class_for_unit(unit)

        if int(acc.get("meter_count", 0)) > 0:
            _add_sensor(
                sensors=sensors,
                key=f"{endpoint_name}_meters_{group_key}_readout_total",
                name=f"{group_label} Total Meter Reading",
                native_value=float(acc["total"]),
                native_unit=unit,
                icon=meta.get("icon"),
                device_class=device_class,
                state_class="total_increasing",
                suggested_display_precision=3,
                attributes={
                    "group": group_key.upper(),
                    "scope": "meters_readout_total",
                    "meter_count": int(acc["meter_count"]),
                    "meter_identifiers": sorted(set(acc["identifiers"])),
                    "last_readout_date": acc.get("latest_readout_date"),
                    "source_endpoint": endpoint_name,
                    "description": (
                        f"Sum of all {group_label.lower()} meter readings"
                        f" ({int(acc['meter_count'])} meters). Cumulative value."
                    ),
                    **dict(window_attributes or {}),
                },
            )

        if int(acc.get("meter_count_kwh", 0)) > 0:
            _add_sensor(
                sensors=sensors,
                key=f"{endpoint_name}_meters_{group_key}_energy_total",
                name=f"{group_label} Total Energy",
                native_value=float(acc["total_kwh"]),
                native_unit="kWh",
                icon="mdi:flash",
                device_class="energy",
                state_class="total_increasing",
                suggested_display_precision=3,
                attributes={
                    "group": group_key.upper(),
                    "scope": "meters_energy_total",
                    "meter_count": int(acc["meter_count_kwh"]),
                    "meter_identifiers": sorted(set(acc["identifiers"])),
                    "last_readout_date": acc.get("latest_readout_date"),
                    "source_endpoint": endpoint_name,
                    "description": (
                        f"Sum of estimated kWh consumption across all {group_label.lower()} meters"
                        f" ({int(acc['meter_count_kwh'])} meters). Suitable for the Energy Dashboard."
                    ),
                    **dict(window_attributes or {}),
                },
            )


def _apply_sensor_presentation_defaults(
    sensors: dict[str, dict[str, Any]],
) -> None:
    """Set default visibility/category to keep the entity list practical."""
    for key, descriptor in sensors.items():
        comparison_core = (
            key.startswith("comparison_")
            and (
                "_current_vs_previous_month_" in key
                or key.endswith("_delta_percent_total")
                or "_current_month_comparison" in key
                or "_current_month_delta_percent" in key
            )
        )
        advanced = (
            key == "estate_units_count"
            or (key.startswith("comparison_") and not comparison_core)
            or key.startswith("summary_benchmark_")
            or key.startswith("summary_real_estate_average_")
            or "_real_estate_average_latest_" in key
            or "_estate_unit_totals_" in key
            # Absolute delta sensors are less useful than %; keep them diagnostic
            or key.endswith("_delta_absolute")
        )

        descriptor["enabled_default"] = not advanced
        if advanced:
            descriptor["entity_category"] = "diagnostic"


def _add_sensor(
    sensors: dict[str, dict[str, Any]],
    key: str,
    name: str,
    native_value: Any,
    native_unit: str | None = None,
    icon: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    suggested_display_precision: int | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> None:
    # HA enforces: device_class water/energy only permits
    # state_class total or total_increasing.  Drop device_class for
    # measurement sensors so the icon still works via the icon field.
    if device_class in ("water", "energy") and state_class not in ("total", "total_increasing"):
        device_class = None

    sensors[key] = {
        "name": name,
        "native_value": native_value,
        "native_unit": native_unit,
        "icon": icon,
        "device_class": device_class,
        "state_class": state_class,
        "suggested_display_precision": suggested_display_precision,
        "attributes": dict(attributes or {}),
    }


def _title_from_endpoint(endpoint_name: str) -> str:
    return endpoint_name.replace("_", " ").title()


def _device_class_for_unit(unit: str | None) -> str | None:
    if unit == "m3":
        return "water"
    if unit == "kWh":
        return "energy"
    return None


def _normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    if unit.lower() in {"m3", "m^3", "m³"}:
        return "m3"
    if unit.lower() in {"kwh"}:
        return "kWh"
    return unit


def _meter_entity_key_component(meter: Mapping[str, Any]) -> str | None:
    identifier = meter.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        return _normalize_key_component(identifier)

    meter_id = meter.get("id")
    if meter_id is None:
        return None
    return _normalize_key_component(meter_id)


def _normalize_key_component(value: Any) -> str:
    text = str(value).strip().lower()
    if text == "":
        return "unknown"
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    return normalized or "unknown"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".")
        if cleaned == "":
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _window_attributes(window_meta: Any) -> dict[str, Any]:
    """Extract selected fetch-window metadata for sensor attributes."""
    if not isinstance(window_meta, Mapping):
        return {}
    selected = window_meta.get("selected_window")
    if not isinstance(selected, Mapping):
        return {}

    attrs: dict[str, Any] = {}
    from_value = selected.get("from")
    to_value = selected.get("to")
    window_label = selected.get("window")
    selection_reason = selected.get("selection_reason")
    latest_readout_date = selected.get("latest_readout_date")

    if from_value is not None:
        attrs["window_from"] = str(from_value)
    if to_value is not None:
        attrs["window_to"] = str(to_value)
    if window_label is not None:
        attrs["window_label"] = str(window_label)
    if selection_reason is not None:
        attrs["window_selection_reason"] = str(selection_reason)
    if latest_readout_date is not None:
        attrs["window_latest_readout_date"] = str(latest_readout_date)

    return attrs


def _period_label_from_window(window_meta: Any) -> str | None:
    """Derive a human-readable period label from the selected query window.

    Examples: ``"Jan 2026"`` (same month), ``"Jan\u2013Mar 2026"`` (same year),
    ``"Nov 2025\u2013Mar 2026"`` (cross-year).
    """
    selected = (
        window_meta.get("selected_window")
        if isinstance(window_meta, Mapping)
        else None
    )
    if not isinstance(selected, Mapping):
        return None
    from_str = selected.get("from")
    to_str = selected.get("to")
    if not isinstance(from_str, str) or not isinstance(to_str, str):
        return None
    try:
        from_date = dt_date.fromisoformat(from_str[:10])
        to_date = dt_date.fromisoformat(to_str[:10])
    except (ValueError, IndexError):
        return None

    from_label = _month_label(from_date.month)
    to_label = _month_label(to_date.month)

    if from_date.year != to_date.year:
        return f"{from_label} {from_date.year}\u2013{to_label} {to_date.year}"
    if from_date.month != to_date.month:
        return f"{from_label}\u2013{to_label} {to_date.year}"
    return f"{from_label} {from_date.year}"


def _latest_date_string(current: Any, candidate: Any) -> str | None:
    """Return the newer ISO date string (YYYY-MM-DD) if parseable."""
    current_date = _parse_date_like(current)
    candidate_date = _parse_date_like(candidate)
    if current_date is None:
        return candidate_date
    if candidate_date is None:
        return current_date
    return candidate_date if candidate_date > current_date else current_date


def _parse_date_like(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) < 10:
        return None
    date_part = text[:10]
    if date_part[4] != "-" or date_part[7] != "-":
        return None
    try:
        dt_date.fromisoformat(date_part)
    except ValueError:
        return None
    return date_part


def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
