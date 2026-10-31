"""Base entity and DeviceInfo for the Librus Synergia integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_STUDENT_ACCOUNT
from .coordinator import LibrusDataUpdateCoordinator


class LibrusEntity(CoordinatorEntity[LibrusDataUpdateCoordinator]):
    """Base entity representing a child's Librus Synergia resource."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LibrusDataUpdateCoordinator,
        entity_key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the Librus entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{entity_key}"
        self._attr_name = name
        if icon:
            self._attr_icon = icon

        class_suffix = ""
        if coordinator.data and coordinator.data.student.class_name:
            class_suffix = f" (Klasa {coordinator.data.student.student_name and coordinator.data.student.class_name})"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=f"Librus - {coordinator.student_display_name}",
            manufacturer=MANUFACTURER,
            model=f"{MODEL_STUDENT_ACCOUNT}{class_suffix}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://synergia.librus.pl",
        )

