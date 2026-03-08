"""Sensors for UVI integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfArea, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BASE_URL, CONF_EMAIL, DOMAIN
from .coordinator import UviDataUpdateCoordinator
from .device_mapping import (
    build_root_device_context,
    derive_device_topology,
    stable_account_key,
)

DEVICE_CLASS_MAP: dict[str, SensorDeviceClass] = {
    "energy": SensorDeviceClass.ENERGY,
    "water": SensorDeviceClass.WATER,
}

STATE_CLASS_MAP: dict[str, SensorStateClass] = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total": SensorStateClass.TOTAL,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}

ENTITY_CATEGORY_MAP: dict[str, EntityCategory] = {
    "diagnostic": EntityCategory.DIAGNOSTIC,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UVI sensors from a config entry."""
    coordinator: UviDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    known_keys: set[str] = set()

    @callback
    def _async_discover_entities() -> None:
        flat_sensors = coordinator.data.get("flat_sensors", {}) if coordinator.data else {}
        if not isinstance(flat_sensors, Mapping):
            return

        new_keys = [key for key in flat_sensors if key not in known_keys]
        if not new_keys:
            return

        entities = [UviDynamicSensor(coordinator, entry, key) for key in sorted(new_keys)]
        known_keys.update(new_keys)
        async_add_entities(entities)

    _async_discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_discover_entities))


class UviDynamicSensor(CoordinatorEntity[UviDataUpdateCoordinator], SensorEntity):
    """Dynamic sensor entity backed by flattened coordinator payload."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: UviDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_key = sensor_key
        self._attr_unique_id = _build_sensor_unique_id(entry, sensor_key)

    @property
    def name(self) -> str:
        """Return entity name."""
        descriptor = self._descriptor
        return str(descriptor.get("name", self._sensor_key))

    @property
    def available(self) -> bool:
        """Return whether entity is available."""
        return super().available and bool(self._descriptor)

    @property
    def native_value(self) -> Any:
        """Return native value."""
        return self._descriptor.get("native_value")

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return native unit of measurement."""
        unit = self._descriptor.get("native_unit")
        if unit == "kWh":
            return UnitOfEnergy.KILO_WATT_HOUR
        if unit == "m3":
            return UnitOfVolume.CUBIC_METERS
        if unit == "m2":
            return UnitOfArea.SQUARE_METERS
        return unit

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return sensor device class."""
        raw_class = self._descriptor.get("device_class")
        if not isinstance(raw_class, str):
            return None
        return DEVICE_CLASS_MAP.get(raw_class)

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return sensor state class."""
        raw_class = self._descriptor.get("state_class")
        if not isinstance(raw_class, str):
            return None
        return STATE_CLASS_MAP.get(raw_class)

    @property
    def icon(self) -> str | None:
        """Return icon."""
        icon = self._descriptor.get("icon")
        return str(icon) if icon else None

    @property
    def suggested_display_precision(self) -> int | None:
        """Return suggested display precision."""
        value = self._descriptor.get("suggested_display_precision")
        if isinstance(value, int):
            return value
        return None

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Control default enablement for high-volume informational sensors."""
        value = self._descriptor.get("enabled_default")
        if isinstance(value, bool):
            return value
        return True

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return entity category when marked as diagnostic."""
        raw_value = self._descriptor.get("entity_category")
        if not isinstance(raw_value, str):
            return None
        return ENTITY_CATEGORY_MAP.get(raw_value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        attrs = self._descriptor.get("attributes")
        if isinstance(attrs, dict):
            return attrs
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return entity device info (estate root + endpoint + per-meter devices)."""
        return _build_entity_device_info(
            coordinator=self.coordinator,
            entry=self._entry,
            descriptor=self._descriptor,
        )

    @property
    def _descriptor(self) -> dict[str, Any]:
        flat = self.coordinator.data.get("flat_sensors", {}) if self.coordinator.data else {}
        if not isinstance(flat, Mapping):
            return {}

        descriptor = flat.get(self._sensor_key)
        if isinstance(descriptor, dict):
            return descriptor
        return {}


def _build_device_info(
    coordinator: UviDataUpdateCoordinator,
    entry: ConfigEntry,
) -> DeviceInfo:
    context = build_root_device_context(
        payload=coordinator.data,
        base_url=str(entry.data.get(CONF_BASE_URL, "")),
        email=str(entry.data.get(CONF_EMAIL, "")),
        fallback_title=entry.title,
    )
    return DeviceInfo(
        identifiers={(DOMAIN, context["root_identifier"])},
        name=context["root_name"],
        manufacturer=context["host"],
        model="Tenant Portal",
        configuration_url=context["base_url"],
    )


def _build_entity_device_info(
    coordinator: UviDataUpdateCoordinator,
    entry: ConfigEntry,
    descriptor: Mapping[str, Any],
) -> DeviceInfo:
    context = build_root_device_context(
        payload=coordinator.data,
        base_url=str(entry.data.get(CONF_BASE_URL, "")),
        email=str(entry.data.get(CONF_EMAIL, "")),
        fallback_title=entry.title,
    )
    attributes = descriptor.get("attributes")
    attrs_mapping = attributes if isinstance(attributes, Mapping) else None
    topology = derive_device_topology(context=context, attributes=attrs_mapping)

    via_identifier = topology.get("via_identifier")
    via_device = (
        (DOMAIN, str(via_identifier))
        if isinstance(via_identifier, str) and via_identifier
        else None
    )

    return DeviceInfo(
        identifiers={(DOMAIN, str(topology["identifier"]))},
        via_device=via_device,
        name=str(topology["name"]),
        manufacturer=context["host"],
        model=str(topology["model"]),
        configuration_url=context["base_url"],
    )


def _build_sensor_unique_id(entry: ConfigEntry, sensor_key: str) -> str:
    return (
        f"{stable_account_key(str(entry.data.get(CONF_BASE_URL, '')), str(entry.data.get(CONF_EMAIL, '')))}"
        f"_{sensor_key}"
    )
