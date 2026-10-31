"""Test fixtures and Home Assistant stubs for running unit tests without a full HA runtime."""

from __future__ import annotations

import sys
import types
from typing import Any


def install_ha_stubs() -> None:
    """Install lightweight Home Assistant module stubs if `homeassistant` is not installed."""
    if "homeassistant" in sys.modules:
        return

    # homeassistant root
    ha_mod = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha_mod

    # homeassistant.const
    const_mod = types.ModuleType("homeassistant.const")
    const_mod.CONF_USERNAME = "username"  # type: ignore[attr-defined]
    const_mod.CONF_PASSWORD = "password"  # type: ignore[attr-defined]

    class Platform:
        SENSOR = "sensor"
        BUTTON = "button"

    const_mod.Platform = Platform  # type: ignore[attr-defined]
    sys.modules["homeassistant.const"] = const_mod

    # homeassistant.core
    core_mod = types.ModuleType("homeassistant.core")

    def callback(func: Any) -> Any:
        return func

    class FakeEventBus:
        def __init__(self) -> None:
            self.fired_events: list[tuple[str, dict[str, Any]]] = []

        def async_fire(self, event_type: str, event_data: dict[str, Any] | None = None) -> None:
            self.fired_events.append((event_type, event_data or {}))

    class FakeConfigEntriesManager:
        def __init__(self) -> None:
            self.updated_entries: list[tuple[Any, dict[str, Any]]] = []

        def async_update_entry(self, entry: Any, data: dict[str, Any] | None = None) -> None:
            if data is not None:
                entry.data = data
            self.updated_entries.append((entry, data or {}))

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}
            self.bus = FakeEventBus()
            self.config_entries = FakeConfigEntriesManager()

    class ServiceCall:
        def __init__(self, data: dict[str, Any] | None = None) -> None:
            self.data = data or {}

    core_mod.callback = callback  # type: ignore[attr-defined]
    core_mod.HomeAssistant = HomeAssistant  # type: ignore[attr-defined]
    core_mod.ServiceCall = ServiceCall  # type: ignore[attr-defined]
    sys.modules["homeassistant.core"] = core_mod

    # homeassistant.exceptions
    exc_mod = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryAuthFailed(Exception):
        pass

    exc_mod.ConfigEntryAuthFailed = ConfigEntryAuthFailed  # type: ignore[attr-defined]
    sys.modules["homeassistant.exceptions"] = exc_mod

    # homeassistant.config_entries
    ce_mod = types.ModuleType("homeassistant.config_entries")

    class AbortFlow(Exception):
        def __init__(self, reason: str) -> None:
            super().__init__(reason)
            self.reason = reason

    class ConfigEntry:
        def __init__(
            self,
            entry_id: str = "entry_1",
            title: str = "Librus - Jan Kowalski",
            data: dict[str, Any] | None = None,
            options: dict[str, Any] | None = None,
        ) -> None:
            self.entry_id = entry_id
            self.title = title
            self.data = data or {}
            self.options = options or {}
            self.runtime_data: Any = None

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

    class ConfigFlow:
        def __init_subclass__(cls, domain: str | None = None, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            cls.DOMAIN = domain

        def __init__(self) -> None:
            self.hass = HomeAssistant()
            self._unique_id: str | None = None
            self._existing_unique_ids: set[str] = set()

        async def async_set_unique_id(self, unique_id: str) -> None:
            self._unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            if self._unique_id and self._unique_id in self._existing_unique_ids:
                raise AbortFlow("already_configured")

        def async_create_entry(
            self,
            *,
            title: str,
            data: dict[str, Any],
            options: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "options": options or {},
                "unique_id": self._unique_id,
            }

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

    class OptionsFlow:
        hass = HomeAssistant()
        config_entry: ConfigEntry

        def __init__(self, config_entry: ConfigEntry | None = None) -> None:
            self.hass = HomeAssistant()
            if config_entry is not None:
                self.config_entry = config_entry

        def async_create_entry(self, *, title: str, data: dict[str, Any]) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
            }

    ce_mod.AbortFlow = AbortFlow  # type: ignore[attr-defined]
    ce_mod.ConfigEntry = ConfigEntry  # type: ignore[attr-defined]
    ce_mod.ConfigFlow = ConfigFlow  # type: ignore[attr-defined]
    ce_mod.ConfigFlowResult = dict  # type: ignore[attr-defined]
    ce_mod.OptionsFlow = OptionsFlow  # type: ignore[attr-defined]
    sys.modules["homeassistant.config_entries"] = ce_mod

    # homeassistant.helpers & submodules
    helpers_mod = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_mod

    storage_mod = types.ModuleType("homeassistant.helpers.storage")

    class Store:
        _shared_memory: dict[str, Any] = {}

        def __init__(self, hass: Any, version: int, key: str) -> None:
            self.hass = hass
            self.version = version
            self.key = key

        async def async_load(self) -> Any:
            return self._shared_memory.get(self.key)

        async def async_save(self, data: Any) -> None:
            self._shared_memory[self.key] = data

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

    storage_mod.Store = Store  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.storage"] = storage_mod

    uc_mod = types.ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __init__(
            self,
            hass: Any,
            logger: Any,
            *,
            config_entry: Any = None,
            name: str,
            update_interval: Any = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.config_entry = config_entry
            self.name = name
            self.update_interval = update_interval
            self.data: Any = None

        async def async_refresh(self) -> None:
            self.data = await self._async_update_data()

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

    class CoordinatorEntity:
        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

        def __class_getitem__(cls, item: Any) -> Any:
            return cls

    uc_mod.UpdateFailed = UpdateFailed  # type: ignore[attr-defined]
    uc_mod.DataUpdateCoordinator = DataUpdateCoordinator  # type: ignore[attr-defined]
    uc_mod.CoordinatorEntity = CoordinatorEntity  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.update_coordinator"] = uc_mod

    dr_mod = types.ModuleType("homeassistant.helpers.device_registry")

    class DeviceEntryType:
        SERVICE = "service"

    class DeviceInfo(dict):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)

    dr_mod.DeviceEntryType = DeviceEntryType  # type: ignore[attr-defined]
    dr_mod.DeviceInfo = DeviceInfo  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.device_registry"] = dr_mod

    ep_mod = types.ModuleType("homeassistant.helpers.entity_platform")
    ep_mod.AddEntitiesCallback = Any  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.entity_platform"] = ep_mod

    # voluptuous stub if missing
    if "voluptuous" not in sys.modules:
        vol_mod = types.ModuleType("voluptuous")
        vol_mod.Schema = lambda s: s  # type: ignore[attr-defined]
        vol_mod.Required = lambda k, default=None: k  # type: ignore[attr-defined]
        vol_mod.Optional = lambda k, default=None: k  # type: ignore[attr-defined]
        vol_mod.All = lambda *args: args  # type: ignore[attr-defined]
        vol_mod.Coerce = lambda t: t  # type: ignore[attr-defined]
        vol_mod.Range = lambda **kwargs: kwargs  # type: ignore[attr-defined]
        sys.modules["voluptuous"] = vol_mod


install_ha_stubs()
