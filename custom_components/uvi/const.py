"""Constants for the UVI integration."""

from __future__ import annotations

from enum import StrEnum

try:
    from homeassistant.const import Platform
except ModuleNotFoundError:  # pragma: no cover - fallback for local parser tests
    class Platform(StrEnum):
        """Fallback Platform enum when Home Assistant is not installed."""

        SENSOR = "sensor"

DOMAIN = "uvi"

DEFAULT_NAME = "UVI Consumption"
DEFAULT_BASE_URL = ""

CONF_BASE_URL = "base_url"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"

DEFAULT_UPDATE_INTERVAL_HOURS = 24
DEFAULT_UPDATE_INTERVAL_MINUTES = 1440
MIN_UPDATE_INTERVAL_HOURS = 1
MAX_UPDATE_INTERVAL_HOURS = 168
MIN_UPDATE_INTERVAL_MINUTES = 5
MAX_UPDATE_INTERVAL_MINUTES = 10080

API_TIMEOUT_SECONDS = 30

ADAPTIVE_WINDOW_CANDIDATE_DAYS: tuple[int, ...] = (1, 2, 3, 7, 14, 30)
HISTORY_BACKFILL_MAX_YEARS = 15

PLATFORMS: list[Platform] = [Platform.SENSOR]

GROUP_METADATA: dict[str, dict[str, str | None]] = {
    "h1": {
        "label": "Heating",
        "raw_unit": "HKV",
        "normalized_unit": "kWh",
        "icon": "mdi:radiator",
    },
    "k1": {
        "label": "Cold Water",
        "raw_unit": "m3",
        "normalized_unit": None,
        "icon": "mdi:water",
    },
    "w1": {
        "label": "Warm Water",
        "raw_unit": "m3",
        "normalized_unit": "kWh",
        "icon": "mdi:water-thermometer",
    },
}

DEFAULT_MONTHLY_COMPARISON_GROUPS: tuple[str, ...] = ("h1", "k1", "w1")
