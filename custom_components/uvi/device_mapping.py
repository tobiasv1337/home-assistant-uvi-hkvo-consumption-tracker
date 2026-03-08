"""Helpers for stable device topology and identifiers."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha1
from typing import Any
from urllib.parse import urlparse

from .const import GROUP_METADATA

ENDPOINT_DEVICE_LABELS: dict[str, str] = {
    "heating": "Heating",
    "cold_water": "Cold Water",
    "warm_water": "Warm Water",
}

GROUP_PREFIX_TO_ENDPOINT: dict[str, str] = {
    "H": "heating",
    "K": "cold_water",
    "W": "warm_water",
}


def stable_account_key(base_url: str, email: str) -> str:
    """Return stable account key derived from base URL + email."""
    normalized_base_url = str(base_url).strip().lower().rstrip("/")
    normalized_email = str(email).strip().lower()
    raw = f"{normalized_base_url}|{normalized_email}"
    return sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize_identifier_component(value: Any) -> str:
    """Normalize arbitrary value into safe identifier component."""
    text = str(value).strip().lower()
    if text == "":
        return "unknown"
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    return normalized or "unknown"


def build_root_device_context(
    payload: Any,
    *,
    base_url: str,
    email: str,
    fallback_title: str,
) -> dict[str, str]:
    """Build stable context for root and child devices."""
    estate_units = _nested_get(payload, "estate_units", "data")
    first_unit = estate_units[0] if isinstance(estate_units, list) and estate_units else {}

    unit_id = "default"
    unit_name = fallback_title
    city = None

    if isinstance(first_unit, Mapping):
        unit_id = str(first_unit.get("id", "default"))
        attributes = first_unit.get("attributes")
        if isinstance(attributes, Mapping):
            unit_name = str(attributes.get("name") or unit_name)
            address = attributes.get("address")
            if isinstance(address, Mapping):
                city = address.get("city")

    host = urlparse(str(base_url)).hostname or "UVI"
    account_key = stable_account_key(base_url=base_url, email=email)
    unit_token = normalize_identifier_component(unit_id)

    root_name = f"UVI {unit_name}" if unit_name else "UVI"
    if city:
        root_name = f"{root_name} ({city})"

    return {
        "account_key": account_key,
        "root_identifier": f"{account_key}_estate_{unit_token}",
        "root_name": root_name,
        "host": host,
        "base_url": str(base_url),
    }


def derive_device_topology(
    *,
    context: Mapping[str, str],
    attributes: Mapping[str, Any] | None,
) -> dict[str, str | None]:
    """Return resolved device topology for one entity descriptor."""
    root_identifier = str(context["root_identifier"])
    base = {
        "identifier": root_identifier,
        "via_identifier": None,
        "name": str(context["root_name"]),
        "model": "Tenant Portal",
    }

    if not isinstance(attributes, Mapping):
        return base

    meter_topology = _derive_meter_topology(context=context, attributes=attributes)
    if meter_topology is not None:
        return meter_topology

    endpoint_profile = _resolve_endpoint_profile(attributes)
    if endpoint_profile is None:
        return base

    endpoint_token, endpoint_label = endpoint_profile
    return {
        "identifier": f"{context['account_key']}_endpoint_{endpoint_token}",
        "via_identifier": root_identifier,
        "name": endpoint_label,
        "model": f"{endpoint_label} Overview",
    }


def _derive_meter_topology(
    *,
    context: Mapping[str, str],
    attributes: Mapping[str, Any],
) -> dict[str, str | None] | None:
    meter_id = attributes.get("meter_id")
    meter_identifier = attributes.get("meter_identifier")
    if meter_id is None and meter_identifier is None:
        return None

    meter_token = normalize_identifier_component(meter_identifier or meter_id)
    meter_display = str(meter_identifier or meter_id)
    room_name = str(attributes.get("room_name") or "").strip()
    room_suffix = f" ({room_name})" if room_name else ""

    return {
        "identifier": f"{context['account_key']}_meter_{meter_token}",
        "via_identifier": str(context["root_identifier"]),
        "name": f"Meter {meter_display}{room_suffix}",
        "model": "Meter",
    }


def _resolve_endpoint_profile(attributes: Mapping[str, Any]) -> tuple[str, str] | None:
    source_endpoint = str(attributes.get("source_endpoint") or "").strip().lower()
    if source_endpoint in ENDPOINT_DEVICE_LABELS:
        return source_endpoint, ENDPOINT_DEVICE_LABELS[source_endpoint]

    # Summary and comparison entities can still be grouped by domain via their group code.
    if source_endpoint in {"summary", "monthly-comparison", "monthly-comparison-historical"}:
        group_raw = str(attributes.get("group") or "").strip()
        if not group_raw:
            return None

        group = group_raw.upper()
        prefix = group[0]
        canonical_endpoint = GROUP_PREFIX_TO_ENDPOINT.get(prefix)
        if canonical_endpoint is not None:
            return canonical_endpoint, ENDPOINT_DEVICE_LABELS[canonical_endpoint]

        metadata = GROUP_METADATA.get(group.lower(), {})
        label = str(metadata.get("label") or f"Group {group}")
        token = f"group_{normalize_identifier_component(group)}"
        return token, label

    return None


def _nested_get(container: Any, *path: str) -> Any:
    current = container
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
