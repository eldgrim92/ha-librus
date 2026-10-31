"""Config flow and Options flow for the Librus Synergia integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .api import (
    LibrusApiClient,
    LibrusAuthError,
    LibrusConnectionError,
    StudentProfile,
)
from .const import (
    CONF_MAX_ITEMS,
    CONF_STUDENT_NAME,
    CONF_SYNC_INTERVAL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    DOMAIN,
    MAX_MAX_ITEMS,
    MAX_SYNC_INTERVAL_MINUTES,
    MIN_MAX_ITEMS,
    MIN_SYNC_INTERVAL_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


async def async_validate_credentials(
    username: str,
    password: str,
) -> StudentProfile:
    """Authenticate with Librus and return the student's profile."""
    client = LibrusApiClient(username=username, password=password)
    try:
        await client.async_authenticate()
        return await client.async_get_student_profile()
    finally:
        await client.async_close()


class LibrusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Librus Synergia (supports adding 1 or more kids)."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LibrusOptionsFlowHandler:
        """Return the options flow handler for configuring sync period and limits."""
        return LibrusOptionsFlowHandler()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step where a parent/student adds a child's Librus account."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            custom_name = (user_input.get(CONF_STUDENT_NAME) or "").strip()
            sync_interval = int(
                user_input.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_MINUTES)
            )
            max_items = int(user_input.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS))

            try:
                profile = await async_validate_credentials(username, password)
            except LibrusAuthError:
                errors["base"] = "invalid_auth"
            except LibrusConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Librus setup")
                errors["base"] = "unknown"
            else:
                unique_id = f"{DOMAIN}_{profile.account_id}_{username.lower()}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                student_display_name = custom_name or profile.student_name or username
                title = f"Librus - {student_display_name}"

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_STUDENT_NAME: student_display_name,
                    },
                    options={
                        CONF_SYNC_INTERVAL: sync_interval,
                        CONF_MAX_ITEMS: max_items,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_STUDENT_NAME, default=""): str,
                vol.Optional(
                    CONF_SYNC_INTERVAL,
                    default=DEFAULT_SYNC_INTERVAL_MINUTES,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SYNC_INTERVAL_MINUTES,
                        max=MAX_SYNC_INTERVAL_MINUTES,
                    ),
                ),
                vol.Optional(
                    CONF_MAX_ITEMS,
                    default=DEFAULT_MAX_ITEMS,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_MAX_ITEMS, max=MAX_MAX_ITEMS),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class LibrusOptionsFlowHandler(OptionsFlow):
    """Handle dynamic options for a child's Librus integration (e.g., sync interval)."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the Librus options (synchronization period, history size, optional password update)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            sync_interval = int(
                user_input.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_MINUTES)
            )
            max_items = int(user_input.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS))
            new_password = (user_input.get(CONF_PASSWORD) or "").strip()

            if new_password:
                username = self.config_entry.data[CONF_USERNAME]
                try:
                    await async_validate_credentials(username, new_password)
                except LibrusAuthError:
                    errors["base"] = "invalid_auth"
                except LibrusConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error validating updated Librus password")
                    errors["base"] = "unknown"
                else:
                    new_data = {
                        **self.config_entry.data,
                        CONF_PASSWORD: new_password,
                    }
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=new_data,
                    )

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SYNC_INTERVAL: sync_interval,
                        CONF_MAX_ITEMS: max_items,
                    },
                )

        current_interval = self.config_entry.options.get(
            CONF_SYNC_INTERVAL,
            DEFAULT_SYNC_INTERVAL_MINUTES,
        )
        current_max_items = self.config_entry.options.get(
            CONF_MAX_ITEMS,
            DEFAULT_MAX_ITEMS,
        )

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SYNC_INTERVAL,
                    default=current_interval,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_SYNC_INTERVAL_MINUTES,
                        max=MAX_SYNC_INTERVAL_MINUTES,
                    ),
                ),
                vol.Required(
                    CONF_MAX_ITEMS,
                    default=current_max_items,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_MAX_ITEMS, max=MAX_MAX_ITEMS),
                ),
                vol.Optional(CONF_PASSWORD, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )

