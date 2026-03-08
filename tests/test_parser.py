"""Tests for UVI payload parser."""

from __future__ import annotations

import json

import pytest

from custom_components.uvi.parser import build_flat_sensors


def test_build_flat_sensors_summary_and_monthly() -> None:
    payload = {
        "summary": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "3177.336",
                                "normalized_kwh_consumption": "3272.65608",
                                "status": "calculation",
                            }
                        }
                    }
                }
            }
        },
        "heating": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "2463.391",
                                "normalized_kwh_consumption": "2537.29273",
                                "status": "calculation",
                            }
                        },
                        "month_by_month": {
                            "2026": {
                                "2": {
                                    "H1": {
                                        "consumption": "2463.391",
                                        "normalized_kwh_consumption": "2537.29273",
                                        "status": "calculation",
                                    }
                                }
                            }
                        },
                    }
                }
            }
        },
        "monthly_comparison": {
            "h1": {
                "data": {
                    "attributes": {
                        "group": "h1",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "3177.34", "unit": "HKV"},
                                {"month": 2, "quantity": "2463.39", "unit": "HKV"},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "2351.68", "unit": "HKV"},
                                {"month": 2, "quantity": "2090.66", "unit": "HKV"},
                            ],
                        },
                    }
                }
            }
        },
        "estate_units": {"data": [{"id": "241078", "attributes": {"name": "0018"}}]},
    }

    sensors = build_flat_sensors(payload)

    assert "summary_current_h1_consumption" in sensors
    assert sensors["summary_current_h1_consumption"]["native_value"] == 3177.336

    assert "heating_current_month_h1_normalized_kwh" in sensors
    assert sensors["heating_current_month_h1_normalized_kwh"]["native_value"] == 2537.29273

    assert "comparison_h1_base_total" in sensors
    assert round(sensors["comparison_h1_base_total"]["native_value"], 2) == 5640.73

    assert "estate_units_count" in sensors
    assert sensors["estate_units_count"]["native_value"] == 1


def test_build_flat_sensors_unknown_group_uses_monthly_unit() -> None:
    payload = {
        "summary": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {
                            "x9": {
                                "consumption": "12.34",
                                "status": "calculation",
                            }
                        }
                    }
                }
            }
        },
        "monthly_comparison": {
            "x9": {
                "data": {
                    "attributes": {
                        "group": "x9",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "12.34", "unit": "m3"},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "10.0", "unit": "m3"},
                            ],
                        },
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)

    key = "summary_current_x9_consumption"
    assert key in sensors
    assert sensors[key]["native_unit"] == "m3"
    assert sensors[key]["device_class"] is None  # measurement → no device_class


def test_build_flat_sensors_historical_monthly_comparison() -> None:
    payload = {
        "historical_monthly_comparison": {
            "h1": {
                "loaded": True,
                "base-year": {
                    "2026": [{"month": 1, "quantity": "10", "unit": "HKV"}],
                    "2025": [{"month": 1, "quantity": "8", "unit": "HKV"}],
                },
                "comparison-year": {
                    "2025": [{"month": 1, "quantity": "8", "unit": "HKV"}],
                },
                "comparison-year-climate-corrected": {},
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)
    key = "comparison_h1_historical_entries_count"

    assert key in sensors
    assert sensors[key]["native_value"] == 3
    assert sensors[key]["attributes"]["loaded"] is True
    assert sensors[key]["attributes"]["years_available"] == [2025, 2026]


def test_consumption_sensors_include_selected_window_attributes() -> None:
    payload = {
        "window": {
            "consumption": {
                "heating": {
                    "selected_window": {
                        "from": "2026-02-28",
                        "to": "2026-03-02",
                        "window": "adaptive_3d",
                        "selection_reason": "fallback_best_success",
                        "latest_readout_date": "2026-02-28",
                    }
                }
            }
        },
        "heating": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "2463.391",
                                "normalized_kwh_consumption": "2537.29273",
                                "status": "calculation",
                            }
                        }
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)

    # The 'current' scope was removed; window attributes are now on current_month.
    # We need month_by_month data for current_month to exist.
    # This test verifies window attributes are propagated to current_month sensors.
    assert "heating_current_month_h1_consumption" not in sensors  # No month_by_month data

    # Add month_by_month data and re-test
    payload["heating"]["data"]["attributes"]["calculation"]["month_by_month"] = {
        "2026": {
            "2": {
                "H1": {
                    "consumption": "2463.391",
                    "normalized_kwh_consumption": "2537.29273",
                    "status": "calculation",
                }
            }
        }
    }
    sensors = build_flat_sensors(payload)
    attrs = sensors["heating_current_month_h1_consumption"]["attributes"]

    assert attrs["window_from"] == "2026-02-28"
    assert attrs["window_to"] == "2026-03-02"
    assert attrs["window_label"] == "adaptive_3d"
    assert attrs["window_selection_reason"] == "fallback_best_success"
    assert attrs["window_latest_readout_date"] == "2026-02-28"


def test_summary_comparison_sensors_are_computed() -> None:
    payload = {
        "summary": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {"H1": {"consumption": "2463.391"}},
                        "real_estate_average": {"H1": {"consumption": "2014.71872"}},
                        "benchmark": {"H1": {"consumption": "584.472"}},
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)
    assert "summary_current_vs_building_average_h1_delta_percent" in sensors
    assert "summary_current_vs_average_tenant_h1_delta_percent" in sensors
    assert sensors["summary_current_vs_building_average_h1_delta_percent"]["native_value"] == pytest.approx(
        22.269723090675406
    )


def test_endpoint_previous_month_and_deltas_removed_from_endpoints() -> None:
    """Endpoint previous-month values and deltas were moved to monthly-comparison."""
    payload = {
        "heating": {
            "data": {
                "attributes": {
                    "calculation": {
                        "month_by_month": {
                            "2026": {
                                "1": {"H1": {"consumption": "3177.34", "status": "calculation"}},
                                "2": {"H1": {"consumption": "2463.39", "status": "calculation"}},
                            }
                        }
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)

    # current_month should exist (latest month)
    assert "heating_current_month_h1_consumption" in sensors
    assert sensors["heating_current_month_h1_consumption"]["native_value"] == 2463.39

    # previous_month and deltas should NOT exist (removed from endpoint)
    assert "heating_previous_month_h1_consumption" not in sensors
    assert "heating_current_vs_previous_month_h1_delta_percent" not in sensors
    assert "heating_current_vs_previous_month_h1_delta_absolute" not in sensors

    # The current scope should also NOT exist (removed as duplicate of current_month)
    assert "heating_current_h1_consumption" not in sensors


def test_parser_verbose_report(pytestconfig) -> None:
    """Optionally print parser output in verbose mode."""
    if not getattr(pytestconfig, "uvi_verbose", False):
        return

    payload = {
        "summary": {
            "data": {
                "attributes": {
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "3177.336",
                                "normalized_kwh_consumption": "3272.65608",
                                "status": "calculation",
                            }
                        }
                    }
                }
            }
        },
        "estate_units": {"data": [{"id": "241078", "attributes": {"name": "0018"}}]},
    }

    sensors = build_flat_sensors(payload)
    print("\n=== UVI Parser Report ===")
    print(json.dumps(sensors, indent=2, sort_keys=True, ensure_ascii=True))


def test_heating_detailed_numeric_room_keys_and_multiple_meters() -> None:
    payload = {
        "heating": {
            "data": {
                "attributes": {
                    "calculation": {
                        "detailed": {
                            "1347600": {
                                "H1": {
                                    "name": "Ki",
                                    "meters": [
                                        {
                                            "id": 1236006,
                                            "identifier": "16307034",
                                            "consumption": "274.092",
                                            "last_readout_value": "90.0",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "7.028",
                                            "consumption_without_k_total_coefficient": "39.0",
                                        }
                                    ],
                                }
                            },
                            "1347606": {
                                "H1": {
                                    "name": "Wo",
                                    "meters": [
                                        {
                                            "id": 1236007,
                                            "identifier": "16307035",
                                            "consumption": "719.387",
                                            "last_readout_value": "315.0",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "5.251",
                                            "consumption_without_k_total_coefficient": "137.0",
                                        },
                                        {
                                            "id": 1236008,
                                            "identifier": "16307036",
                                            "consumption": "480.16",
                                            "last_readout_value": "172.0",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "6.002",
                                            "consumption_without_k_total_coefficient": "80.0",
                                        },
                                    ],
                                }
                            },
                        }
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)
    assert "meter_16307034_h1_consumption" in sensors
    assert "meter_16307035_h1_consumption" in sensors
    assert "meter_16307036_h1_consumption" in sensors

    assert sensors["meter_16307034_h1_consumption"]["attributes"]["room_id"] == "1347600"
    assert sensors["meter_16307035_h1_consumption"]["attributes"]["room_id"] == "1347606"
    assert sensors["meter_16307035_h1_consumption"]["attributes"]["room_name"] == "Wo"

    assert "heating_meters_h1_readout_total" in sensors
    assert sensors["heating_meters_h1_readout_total"]["native_value"] == 577.0


def test_incomplete_month_skipped_in_comparison() -> None:
    """The latest month marked incomplete or matching current calendar month is skipped."""
    from datetime import date

    payload = {
        "monthly_comparison": {
            "h1": {
                "data": {
                    "attributes": {
                        "group": "h1",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "3177.34", "unit": "HKV", "incomplete": False},
                                {"month": 2, "quantity": "2463.39", "unit": "HKV", "incomplete": False},
                                {"month": 3, "quantity": "800.00", "unit": "HKV", "incomplete": True},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "2351.68", "unit": "HKV"},
                                {"month": 2, "quantity": "2090.66", "unit": "HKV"},
                                {"month": 3, "quantity": "1900.00", "unit": "HKV"},
                            ],
                        },
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    # With reference_date in March 2026 — month 3 should be skipped
    sensors = build_flat_sensors(payload, reference_date=date(2026, 3, 15))

    # The month-over-month comparison should use month 2 vs month 1 (skipping incomplete month 3)
    attrs = sensors["comparison_h1_current_vs_previous_month_delta_percent"]["attributes"]
    assert attrs["current_month"] == 2
    assert attrs["previous_month"] == 1

    # The same-month-last-year comparison should also use month 2
    attrs_yoy = sensors["comparison_h1_current_month_delta_percent"]["attributes"]
    assert attrs_yoy["month"] == 2


def test_incomplete_month_via_flag_only() -> None:
    """Even without reference_date, the incomplete flag should be respected."""
    payload = {
        "monthly_comparison": {
            "k1": {
                "data": {
                    "attributes": {
                        "group": "k1",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "6.46", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "5.80", "unit": "m3", "incomplete": True},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "6.61", "unit": "m3"},
                                {"month": 2, "quantity": "5.98", "unit": "m3"},
                            ],
                        },
                    }
                }
            }
        },
        "estate_units": {"data": []},
    }

    sensors = build_flat_sensors(payload)

    # Only month 1 is complete — no month-over-month comparison possible
    assert "comparison_k1_current_vs_previous_month_delta_percent" not in sensors

    # Same-month-last-year should use month 1
    assert "comparison_k1_current_month_delta_percent" in sensors
    attrs = sensors["comparison_k1_current_month_delta_percent"]["attributes"]
    assert attrs["month"] == 1
