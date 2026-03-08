"""Unit tests for API endpoint mapping."""

from __future__ import annotations

import asyncio
from typing import Any

from custom_components.uvi.api import UviApiClient


def test_fetch_methods_map_to_expected_paths_and_params(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def _fake_request_json(path: str, params=None, retry_auth: bool = True):
        calls.append(
            {
                "path": path,
                "params": params,
                "retry_auth": retry_auth,
            }
        )
        return {"ok": True, "path": path, "params": params}

    client = UviApiClient(
        session=object(),
        base_url="https://uvi.example.test",
        email="user@example.test",
        password="secret",
    )

    monkeypatch.setattr(client, "_request_json", _fake_request_json)

    async def _run() -> None:
        await client.fetch_user()
        await client.fetch_estate_units()
        await client.fetch_summary("2026-01-01", "2026-01-31")
        await client.fetch_heating("2026-01-01", "2026-01-31")
        await client.fetch_warm_water("2026-01-01", "2026-01-31")
        await client.fetch_cold_water("2026-01-01", "2026-01-31")
        await client.fetch_monthly_comparison("x9", 2026, 2025)

    asyncio.run(_run())

    assert calls == [
        {"path": "/api/user", "params": None, "retry_auth": True},
        {"path": "/api/estate-units", "params": None, "retry_auth": True},
        {
            "path": "/api/summary",
            "params": {"filter[from]": "2026-01-01", "filter[to]": "2026-01-31"},
            "retry_auth": True,
        },
        {
            "path": "/api/heating",
            "params": {"filter[from]": "2026-01-01", "filter[to]": "2026-01-31"},
            "retry_auth": True,
        },
        {
            "path": "/api/warm-water",
            "params": {"filter[from]": "2026-01-01", "filter[to]": "2026-01-31"},
            "retry_auth": True,
        },
        {
            "path": "/api/cold-water",
            "params": {"filter[from]": "2026-01-01", "filter[to]": "2026-01-31"},
            "retry_auth": True,
        },
        {
            "path": "/api/monthly-comparison",
            "params": {
                "filter[base-year]": "2026",
                "filter[comparison-year]": "2025",
                "filter[group]": "x9",
            },
            "retry_auth": True,
        },
    ]


def test_api_endpoint_mapping_verbose_report(pytestconfig, monkeypatch) -> None:
    """Optionally print endpoint mapping when verbose mode is enabled."""
    if not getattr(pytestconfig, "uvi_verbose", False):
        return

    calls: list[dict[str, Any]] = []

    async def _fake_request_json(path: str, params=None, retry_auth: bool = True):
        calls.append(
            {
                "path": path,
                "params": params,
                "retry_auth": retry_auth,
            }
        )
        return {"ok": True}

    client = UviApiClient(
        session=object(),
        base_url="https://uvi.example.test",
        email="user@example.test",
        password="secret",
    )
    monkeypatch.setattr(client, "_request_json", _fake_request_json)

    async def _run() -> None:
        await client.fetch_user()
        await client.fetch_estate_units()
        await client.fetch_summary("2026-01-01", "2026-01-31")
        await client.fetch_heating("2026-01-01", "2026-01-31")
        await client.fetch_warm_water("2026-01-01", "2026-01-31")
        await client.fetch_cold_water("2026-01-01", "2026-01-31")
        await client.fetch_monthly_comparison("x9", 2026, 2025)

    asyncio.run(_run())
    print("\n=== UVI API Endpoint Mapping Report ===")
    for call in calls:
        print(call)
