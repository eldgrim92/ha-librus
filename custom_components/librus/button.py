"""Button platform for triggering an immediate Librus Synergia sync."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LibrusDataUpdateCoordinator
from .entity import LibrusEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the manual sync button for a child's Librus entry."""
    coordinator: LibrusDataUpdateCoordinator = getattr(
        entry, "runtime_data", None
    ) or hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LibrusSyncNowButton(coordinator)])


class LibrusSyncNowButton(LibrusEntity, ButtonEntity):
    """Button entity to trigger an on-demand synchronization with Librus."""

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize the sync button."""
        super().__init__(
            coordinator=coordinator,
            entity_key="sync_now",
            name="Synchronizuj teraz",
            icon="mdi:sync",
        )

    async def async_press(self) -> None:
        """Trigger an immediate refresh of the child's Librus data."""
        await self.coordinator.async_request_refresh()

