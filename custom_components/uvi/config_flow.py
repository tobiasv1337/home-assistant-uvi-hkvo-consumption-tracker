"""Config flow for UVI integration."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import UviApiClient, UviAuthenticationError, UviRequestError
from .const import (
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL_HOURS,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DOMAIN,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _build_user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}

    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(
                CONF_BASE_URL,
                default=defaults.get(CONF_BASE_URL, ""),
            ): str,
            vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_UPDATE_INTERVAL_MINUTES,
                default=defaults.get(
                    CONF_UPDATE_INTERVAL_MINUTES,
                    defaults.get(
                        CONF_UPDATE_INTERVAL_HOURS,
                        DEFAULT_UPDATE_INTERVAL_HOURS * 60,
                    ),
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL_MINUTES,
                    max=MAX_UPDATE_INTERVAL_MINUTES,
                    mode="box",
                    step=5,
                )
            ),
        }
    )


class UviConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UVI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized = _normalize_user_input(user_input)
            try:
                await _async_validate_input(self.hass, normalized)
            except UviAuthenticationError:
                errors["base"] = "invalid_auth"
            except (UviRequestError, ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during config flow")
                errors["base"] = "unknown"
            else:
                unique_id = _build_unique_id(
                    normalized[CONF_BASE_URL], normalized[CONF_EMAIL]
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = normalized.get(CONF_NAME) or _default_title(
                    normalized[CONF_BASE_URL]
                )

                data = {
                    CONF_NAME: normalized.get(CONF_NAME, DEFAULT_NAME),
                    CONF_BASE_URL: normalized[CONF_BASE_URL],
                    CONF_EMAIL: normalized[CONF_EMAIL],
                    CONF_PASSWORD: normalized[CONF_PASSWORD],
                }
                options = {
                    CONF_UPDATE_INTERVAL_MINUTES: int(
                        normalized.get(
                            CONF_UPDATE_INTERVAL_MINUTES,
                            DEFAULT_UPDATE_INTERVAL_MINUTES,
                        )
                    )
                }
                return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, _: dict[str, Any]):
        """Handle reauthentication initiated by Home Assistant."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Confirm reauthentication."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}

        if user_input is not None:
            merged = _normalize_user_input(
                {
                    CONF_NAME: entry.data.get(CONF_NAME, DEFAULT_NAME),
                    CONF_BASE_URL: entry.data[CONF_BASE_URL],
                    CONF_EMAIL: user_input.get(CONF_EMAIL, entry.data[CONF_EMAIL]),
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_UPDATE_INTERVAL_MINUTES: entry.options.get(
                        CONF_UPDATE_INTERVAL_MINUTES,
                        entry.options.get(
                            CONF_UPDATE_INTERVAL_HOURS,
                            DEFAULT_UPDATE_INTERVAL_HOURS * 60,
                        ),
                    ),
                }
            )

            try:
                await _async_validate_input(self.hass, merged)
            except UviAuthenticationError:
                errors["base"] = "invalid_auth"
            except (UviRequestError, ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                updated_unique_id = _build_unique_id(
                    merged[CONF_BASE_URL],
                    merged[CONF_EMAIL],
                )
                if _is_unique_id_configured_for_other_entry(
                    hass=self.hass,
                    unique_id=updated_unique_id,
                    current_entry_id=entry.entry_id,
                ):
                    return self.async_abort(reason="already_configured")

                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_EMAIL: merged[CONF_EMAIL],
                        CONF_PASSWORD: merged[CONF_PASSWORD],
                    },
                    unique_id=updated_unique_id,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=entry.data[CONF_EMAIL]): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> UviOptionsFlow:
        """Get the options flow handler."""
        return UviOptionsFlow()


class UviOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for UVI."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_UPDATE_INTERVAL_MINUTES: int(
                        user_input[CONF_UPDATE_INTERVAL_MINUTES]
                    )
                },
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL_MINUTES,
                    default=self.config_entry.options.get(
                        CONF_UPDATE_INTERVAL_MINUTES,
                        self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL_HOURS,
                            DEFAULT_UPDATE_INTERVAL_HOURS * 60,
                        ),
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL_MINUTES,
                        max=MAX_UPDATE_INTERVAL_MINUTES,
                        mode="box",
                        step=5,
                    )
                )
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


def _normalize_user_input(user_input: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(user_input)
    base_url = str(normalized.get(CONF_BASE_URL, "")).strip()
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        base_url = f"https://{base_url}"
    normalized[CONF_BASE_URL] = base_url.rstrip("/")

    normalized[CONF_EMAIL] = str(normalized.get(CONF_EMAIL, "")).strip().lower()
    normalized[CONF_PASSWORD] = str(normalized.get(CONF_PASSWORD, ""))
    normalized[CONF_NAME] = str(normalized.get(CONF_NAME, DEFAULT_NAME)).strip()

    interval = normalized.get(
        CONF_UPDATE_INTERVAL_MINUTES,
        normalized.get(
            CONF_UPDATE_INTERVAL_HOURS,
            DEFAULT_UPDATE_INTERVAL_MINUTES,
        ),
    )
    normalized[CONF_UPDATE_INTERVAL_MINUTES] = int(float(interval))
    return normalized


def _build_unique_id(base_url: str, email: str) -> str:
    return f"{base_url.lower()}|{email.lower()}"


def _default_title(base_url: str) -> str:
    host = urlparse(base_url).hostname or base_url
    return f"UVI ({host})"


def _is_unique_id_configured_for_other_entry(
    hass,
    unique_id: str,
    current_entry_id: str,
) -> bool:
    for configured_entry in hass.config_entries.async_entries(DOMAIN):
        if configured_entry.entry_id == current_entry_id:
            continue
        if configured_entry.unique_id == unique_id:
            return True
    return False


async def _async_validate_input(hass, data: dict[str, Any]) -> None:
    """Validate credentials by calling /api/user."""
    session = async_get_clientsession(hass)
    client = UviApiClient(
        session=session,
        base_url=data[CONF_BASE_URL],
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
    )

    user_payload = await client.fetch_user()
    user_id = user_payload.get("data", {}).get("id")
    if not user_id:
        raise UviRequestError(
            message="User endpoint returned no id",
            path="/api/user",
            status=None,
        )
