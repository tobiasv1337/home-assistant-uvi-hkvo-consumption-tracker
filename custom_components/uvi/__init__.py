"""The UVI integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UVI from a config entry."""
    from homeassistant.const import CONF_NAME
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import UviApiClient
    from .const import (
        CONF_BASE_URL,
        CONF_EMAIL,
        CONF_PASSWORD,
        CONF_UPDATE_INTERVAL_HOURS,
        CONF_UPDATE_INTERVAL_MINUTES,
        DEFAULT_UPDATE_INTERVAL_HOURS,
        DEFAULT_UPDATE_INTERVAL_MINUTES,
        PLATFORMS,
    )
    from .coordinator import UviDataUpdateCoordinator

    session = async_get_clientsession(hass)

    update_interval_minutes = int(
        entry.options.get(
            CONF_UPDATE_INTERVAL_MINUTES,
            entry.data.get(
                CONF_UPDATE_INTERVAL_MINUTES,
                int(
                    float(
                        entry.options.get(
                            CONF_UPDATE_INTERVAL_HOURS,
                            entry.data.get(
                                CONF_UPDATE_INTERVAL_HOURS,
                                DEFAULT_UPDATE_INTERVAL_HOURS,
                            ),
                        )
                    )
                    * 60
                ),
            ),
        )
    )
    if update_interval_minutes <= 0:
        update_interval_minutes = DEFAULT_UPDATE_INTERVAL_MINUTES

    api = UviApiClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = UviDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        api=api,
        update_interval=timedelta(minutes=update_interval_minutes),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "name": entry.data.get(CONF_NAME),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .const import PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
