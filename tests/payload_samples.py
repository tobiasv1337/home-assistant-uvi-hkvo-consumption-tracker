"""Sample payload builders for parser tests."""

from __future__ import annotations

from typing import Any


def build_full_payload() -> dict[str, Any]:
    """Return a representative full payload across all supported endpoints."""
    return {
        "summary": {
            "data": {
                "attributes": {
                    "estate-unit": {
                        "id": 241078,
                        "real_estate_id": 13339,
                        "heated_area": "79.52",
                        "warm_water_area": "79.52",
                        "area": "79.52",
                        "name": "0018",
                        "position": "2.OG re",
                        "account_id": 262,
                    },
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "3177.336",
                                "normalized_kwh_consumption": "3272.65608",
                                "status": "calculation",
                            },
                            "K1": {
                                "consumption": "6.463",
                                "normalized_kwh_consumption": None,
                                "status": "calculation",
                            },
                            "W1": {
                                "consumption": "1.903",
                                "normalized_kwh_consumption": "110.65945",
                                "status": "calculation",
                            },
                        },
                        "real_estate_average": {
                            "H1": {
                                "consumption": "2612.70",
                                "status": "calculation",
                            },
                            "K1": {
                                "consumption": "5.00",
                                "status": "calculation",
                            },
                            "W1": {
                                "consumption": "1.66",
                                "status": "calculation",
                            },
                        },
                        "benchmark": {
                            "H1": {"consumption": "662.40"},
                            "W1": {"consumption": "94.27"},
                        },
                    }
                }
            }
        },
        "heating": {
            "data": {
                "attributes": {
                    "estate-unit": {
                        "id": 241078,
                        "real_estate_id": 13339,
                        "heated_area": "79.52",
                        "warm_water_area": "79.52",
                        "area": "79.52",
                        "name": "0018",
                        "position": "2.OG re",
                        "account_id": 262,
                    },
                    "calculation": {
                        "current": {
                            "H1": {
                                "consumption": "2463.391",
                                "normalized_kwh_consumption": "2537.29273",
                                "status": "calculation",
                            }
                        },
                        "estate_unit_totals": {
                            "current": {
                                "H1": {
                                    "consumption": "2463.391",
                                    "normalized_kwh_consumption": "2537.29273",
                                    "status": "calculation",
                                }
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
                        "real_estate_average": {
                            "2026": {
                                "2": {
                                    "H1": "2014.71872",
                                    "H2": "0.0",
                                },
                                "total": {
                                    "H1": "4029.43744",
                                    "H2": "0.0",
                                },
                            }
                        },
                        "detailed": {
                            "room-1": {
                                "H1": {
                                    "name": "Living",
                                    "meters": [
                                        {
                                            "id": 1001,
                                            "identifier": "HEAT-1001",
                                            "consumption": "274.092",
                                            "first_readout_value": "51.0",
                                            "last_readout_value": "90.0",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "7.028",
                                            "consumption_without_k_total_coefficient": "39.0",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:17:18 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": "282.31476",
                                        }
                                    ],
                                }
                            },
                            "room-2": {
                                "H1": {
                                    "name": "Bedroom",
                                    "meters": [
                                        {
                                            "id": 1002,
                                            "identifier": "HEAT-1002",
                                            "consumption": "185.426",
                                            "first_readout_value": "80.0",
                                            "last_readout_value": "138.0",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "3.197",
                                            "consumption_without_k_total_coefficient": "58.0",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:43:01 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": "190.98878",
                                        }
                                    ],
                                }
                            },
                        },
                    }
                }
            }
        },
        "warm_water": {
            "data": {
                "attributes": {
                    "estate-unit": {
                        "id": 241078,
                        "real_estate_id": 13339,
                        "heated_area": "79.52",
                        "warm_water_area": "79.52",
                        "area": "79.52",
                        "name": "0018",
                        "position": "2.OG re",
                        "account_id": 262,
                    },
                    "calculation": {
                        "current": {
                            "W1": {
                                "consumption": "1.956",
                                "normalized_kwh_consumption": "113.7414",
                                "status": "calculation",
                            }
                        },
                        "month_by_month": {
                            "2026": {
                                "2": {
                                    "W1": {
                                        "consumption": "1.956",
                                        "normalized_kwh_consumption": "113.7414",
                                        "status": "calculation",
                                    }
                                }
                            }
                        },
                        "real_estate_average": {
                            "2026": {
                                "2": {"W1": "1.5904"},
                                "total": {"W1": "3.1808"},
                            }
                        },
                        "detailed": {
                            "bath": {
                                "W1": {
                                    "name": "Bath",
                                    "meters": [
                                        {
                                            "id": 2001,
                                            "identifier": "WW-2001",
                                            "consumption": "1.956",
                                            "first_readout_value": "26.554",
                                            "last_readout_value": "28.510",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "1.0",
                                            "consumption_without_k_total_coefficient": "1.956",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:44:13 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": "113.7414",
                                        },
                                        {
                                            "id": 2002,
                                            "identifier": "WW-2002",
                                            "consumption": "0.500",
                                            "first_readout_value": "10.000",
                                            "last_readout_value": "10.500",
                                            "last_readout_date": "2026-02-21",
                                            "k_total_coefficient": "1.0",
                                            "consumption_without_k_total_coefficient": "0.500",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:44:55 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": "29.075",
                                        },
                                    ],
                                }
                            }
                        },
                    }
                }
            }
        },
        "cold_water": {
            "data": {
                "attributes": {
                    "estate-unit": {
                        "id": 241078,
                        "real_estate_id": 13339,
                        "heated_area": "79.52",
                        "warm_water_area": "79.52",
                        "area": "79.52",
                        "name": "0018",
                        "position": "2.OG re",
                        "account_id": 262,
                    },
                    "calculation": {
                        "current": {"K1": {"consumption": "5.802", "status": "calculation"}},
                        "month_by_month": {
                            "2026": {
                                "2": {
                                    "K1": {
                                        "consumption": "5.802",
                                        "normalized_kwh_consumption": None,
                                        "status": "calculation",
                                    }
                                }
                            }
                        },
                        "real_estate_average": {
                            "2026": {
                                "2": {"K1": "4.61216"},
                                "total": {"K1": "9.22432"},
                            }
                        },
                        "detailed": {
                            "bath": {
                                "K1": {
                                    "name": "Bath",
                                    "meters": [
                                        {
                                            "id": 3001,
                                            "identifier": "CW-3001",
                                            "consumption": "1.956",
                                            "first_readout_value": "26.554",
                                            "last_readout_value": "28.510",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "1.0",
                                            "consumption_without_k_total_coefficient": "1.956",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:44:13 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": None,
                                        },
                                        {
                                            "id": 3002,
                                            "identifier": "CW-3002",
                                            "consumption": "3.846",
                                            "first_readout_value": "64.952",
                                            "last_readout_value": "68.798",
                                            "last_readout_date": "2026-02-28",
                                            "k_total_coefficient": "1.0",
                                            "consumption_without_k_total_coefficient": "3.846",
                                            "status": "calculation",
                                            "start_date": "2024-11-12 11:44:55 UTC",
                                            "end_date": None,
                                            "normalized_kwh_consumption": None,
                                        },
                                    ],
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
                                {"month": 1, "quantity": "3177.34", "unit": "HKV", "incomplete": False},
                                {"month": 2, "quantity": "2463.39", "unit": "HKV", "incomplete": False},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "2351.68", "unit": "HKV", "incomplete": False},
                                {"month": 2, "quantity": "2090.66", "unit": "HKV", "incomplete": False},
                            ],
                        },
                        "comparison-year-climate-corrected": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "3028.80", "unit": "HKV", "incomplete": False},
                                {"month": 2, "quantity": "2090.66", "unit": "HKV", "incomplete": False},
                            ],
                        },
                    }
                }
            },
            "k1": {
                "data": {
                    "attributes": {
                        "group": "k1",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "6.46", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "5.80", "unit": "m3", "incomplete": False},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "6.61", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "5.98", "unit": "m3", "incomplete": False},
                            ],
                        },
                        "comparison-year-climate-corrected": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "8.51", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "5.98", "unit": "m3", "incomplete": False},
                            ],
                        },
                    }
                }
            },
            "w1": {
                "data": {
                    "attributes": {
                        "group": "w1",
                        "base-year": {
                            "year": 2026,
                            "consumptions": [
                                {"month": 1, "quantity": "1.90", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "1.96", "unit": "m3", "incomplete": False},
                            ],
                        },
                        "comparison-year": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "1.92", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "1.73", "unit": "m3", "incomplete": False},
                            ],
                        },
                        "comparison-year-climate-corrected": {
                            "year": 2025,
                            "consumptions": [
                                {"month": 1, "quantity": "2.47", "unit": "m3", "incomplete": False},
                                {"month": 2, "quantity": "1.73", "unit": "m3", "incomplete": False},
                            ],
                        },
                    }
                }
            },
        },
        "historical_monthly_comparison": {
            "h1": {
                "loaded": True,
                "base-year": {
                    "2026": [{"month": 1, "quantity": "3177.34", "unit": "HKV"}],
                    "2025": [{"month": 1, "quantity": "2351.68", "unit": "HKV"}],
                },
                "comparison-year": {
                    "2025": [{"month": 1, "quantity": "2351.68", "unit": "HKV"}],
                },
                "comparison-year-climate-corrected": {},
            }
        },
        "estate_units": {
            "data": [
                {
                    "id": "241078",
                    "attributes": {
                        "name": "0018",
                        "address": {
                            "street": "Brueckenstrasse 22 R",
                            "postal-code": "12439",
                            "city": "Berlin",
                        },
                    },
                }
            ]
        },
    }
