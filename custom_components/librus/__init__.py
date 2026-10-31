"""The Librus Synergia integration for Home Assistant."""

from __future__ import annotations

import logging

from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .api import LibrusApiClient
from .const import (
    CONF_MAX_ITEMS,
    CONF_SYNC_INTERVAL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import LibrusDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

LibrusConfigEntry: TypeAlias = ConfigEntry[LibrusDataUpdateCoordinator]

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Set up Librus Synergia for a child from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]
    max_items: int = int(entry.options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS))

    client = LibrusApiClient(
        username=username,
        password=password,
        max_items=max_items,
    )

    coordinator = LibrusDataUpdateCoordinator(
        hass=hass,
        entry=entry,
        client=client,
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        async def _async_handle_refresh(call: ServiceCall) -> None:
            """Refresh all configured Librus child accounts (or a specific entry_id)."""
            target_entry_id = call.data.get("entry_id")
            coordinators: dict[str, LibrusDataUpdateCoordinator] = hass.data.get(
                DOMAIN, {}
            )
            for entry_id, coord in coordinators.items():
                if target_entry_id and entry_id != target_entry_id:
                    continue
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, SERVICE_REFRESH, _async_handle_refresh)

    return True


async def async_reload_options(hass: HomeAssistant, entry: LibrusConfigEntry) -> None:
    """Handle options update (e.g., modified synchronization interval or max items)."""
    coordinator: LibrusDataUpdateCoordinator | None = getattr(
        entry, "runtime_data", None
    ) or hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return

    sync_interval = int(
        entry.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_MINUTES)
    )
    max_items = int(entry.options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS))
    coordinator.update_options(
        sync_interval_minutes=sync_interval,
        max_items=max_items,
    )
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: LibrusConfigEntry) -> bool:
    """Unload a config entry and close its Librus API session."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: LibrusDataUpdateCoordinator | None = hass.data[DOMAIN].pop(
            entry.entry_id, None
        ) or getattr(entry, "runtime_data", None)
        if coordinator is not None:
            await coordinator.client.async_close()

        if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_REFRESH):
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)

    return unload_ok

