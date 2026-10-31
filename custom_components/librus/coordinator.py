"""DataUpdateCoordinator, persistent diff state, and Event Bus triggers for Librus Synergia."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    LibrusApiClient,
    LibrusApiError,
    LibrusAuthError,
    LibrusDataSnapshot,
    LibrusGrade,
    LibrusMessage,
    LibrusNote,
)
from .const import (
    CONF_MAX_ITEMS,
    CONF_STUDENT_NAME,
    CONF_SYNC_INTERVAL,
    DEFAULT_MAX_ITEMS,
    DEFAULT_SYNC_INTERVAL_MINUTES,
    DOMAIN,
    EVENT_NEW_GRADE,
    EVENT_NEW_MESSAGE,
    EVENT_NEW_NOTE,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def compute_new_items(
    seen_ids: set[str],
    current_items: list[Any],
    id_getter: Any,
) -> tuple[list[Any], set[str]]:
    """Return newly arrived items and updated seen_ids set.

    Items in `current_items` are ordered newest-first; notifications are returned
    oldest-first so push notifications arrive in chronological order.
    """
    current_ids = {str(id_getter(item)) for item in current_items if id_getter(item)}
    new_items = [
        item
        for item in reversed(current_items)
        if str(id_getter(item)) and str(id_getter(item)) not in seen_ids
    ]
    updated_seen = seen_ids | current_ids
    return new_items, updated_seen


class LibrusDataUpdateCoordinator(DataUpdateCoordinator[LibrusDataSnapshot]):
    """Coordinator for polling a child's Librus account and firing push notification events."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: LibrusApiClient,
    ) -> None:
        """Initialize the coordinator for a specific child config entry."""
        self.entry = entry
        self.client = client
        self.student_display_name: str = entry.data.get(CONF_STUDENT_NAME) or entry.title

        sync_minutes = int(
            entry.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL_MINUTES)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=sync_minutes),
        )

        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{entry.entry_id}",
        )
        self._state_loaded = False
        self._initialized_baseline = False
        self._seen_message_ids: set[str] = set()
        self._seen_grade_ids: set[str] = set()
        self._seen_note_ids: set[str] = set()

    def update_options(self, sync_interval_minutes: int, max_items: int) -> None:
        """Dynamically update polling period and max items from OptionsFlow."""
        self.update_interval = timedelta(minutes=sync_interval_minutes)
        self.client.max_items = max_items
        _LOGGER.info(
            "Updated Librus sync options for %s: interval=%s min, max_items=%s",
            self.student_display_name,
            sync_interval_minutes,
            max_items,
        )

    async def _async_load_seen_state(self) -> None:
        """Load persisted seen IDs from Home Assistant storage."""
        if self._state_loaded:
            return

        stored = await self._store.async_load()
        if isinstance(stored, dict) and stored.get("initialized"):
            self._initialized_baseline = True
            self._seen_message_ids = set(stored.get("message_ids", []))
            self._seen_grade_ids = set(stored.get("grade_ids", []))
            self._seen_note_ids = set(stored.get("note_ids", []))

        self._state_loaded = True

    async def _async_save_seen_state(self) -> None:
        """Persist seen IDs to Home Assistant storage."""
        await self._store.async_save(
            {
                "initialized": self._initialized_baseline,
                "message_ids": sorted(self._seen_message_ids),
                "grade_ids": sorted(self._seen_grade_ids),
                "note_ids": sorted(self._seen_note_ids),
            }
        )

    async def _async_update_data(self) -> LibrusDataSnapshot:
        """Fetch latest data from Librus and fire push notification events for new items."""
        await self._async_load_seen_state()

        try:
            snapshot = await self.client.async_fetch_snapshot()
        except LibrusAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for {self.student_display_name}: {err}"
            ) from err
        except LibrusApiError as err:
            raise UpdateFailed(
                f"Error communicating with Librus for {self.student_display_name}: {err}"
            ) from err

        if snapshot.student.student_name and not self.entry.data.get(CONF_STUDENT_NAME):
            self.student_display_name = snapshot.student.student_name

        await self._async_process_deltas_and_fire_events(snapshot)
        return snapshot

    async def _async_process_deltas_and_fire_events(
        self,
        snapshot: LibrusDataSnapshot,
    ) -> None:
        """Compare fetched snapshot against seen IDs and fire HA Event Bus events."""
        if not self._initialized_baseline:
            # First run ever: seed seen IDs so existing historical items don't spam notifications
            self._seen_message_ids = {m.message_id for m in snapshot.messages if m.message_id}
            self._seen_grade_ids = {g.grade_id for g in snapshot.grades if g.grade_id}
            self._seen_note_ids = {n.note_id for n in snapshot.notes if n.note_id}
            self._initialized_baseline = True
            await self._async_save_seen_state()
            return

        new_messages, self._seen_message_ids = compute_new_items(
            self._seen_message_ids,
            snapshot.messages,
            lambda m: m.message_id,
        )
        new_grades, self._seen_grade_ids = compute_new_items(
            self._seen_grade_ids,
            snapshot.grades,
            lambda g: g.grade_id,
        )
        new_notes, self._seen_note_ids = compute_new_items(
            self._seen_note_ids,
            snapshot.notes,
            lambda n: n.note_id,
        )

        for msg in new_messages:
            self._fire_new_message_event(msg)

        for grade in new_grades:
            self._fire_new_grade_event(grade)

        for note in new_notes:
            self._fire_new_note_event(note)

        if new_messages or new_grades or new_notes:
            await self._async_save_seen_state()

    def _fire_new_message_event(self, message: LibrusMessage) -> None:
        """Fire `librus_new_message` on the Home Assistant Event Bus."""
        payload = {
            "entry_id": self.entry.entry_id,
            "student_name": self.student_display_name,
            **message.to_attribute_dict(),
        }
        _LOGGER.info(
            "New Librus message for %s from %s: %s",
            self.student_display_name,
            message.sender,
            message.subject,
        )
        self.hass.bus.async_fire(EVENT_NEW_MESSAGE, payload)

    def _fire_new_grade_event(self, grade: LibrusGrade) -> None:
        """Fire `librus_new_grade` on the Home Assistant Event Bus."""
        payload = {
            "entry_id": self.entry.entry_id,
            "student_name": self.student_display_name,
            **grade.to_attribute_dict(),
        }
        _LOGGER.info(
            "New Librus grade for %s in %s: %s",
            self.student_display_name,
            grade.subject,
            grade.value,
        )
        self.hass.bus.async_fire(EVENT_NEW_GRADE, payload)

    def _fire_new_note_event(self, note: LibrusNote) -> None:
        """Fire `librus_new_note` on the Home Assistant Event Bus."""
        payload = {
            "entry_id": self.entry.entry_id,
            "student_name": self.student_display_name,
            **note.to_attribute_dict(),
        }
        _LOGGER.info(
            "New Librus note (%s) for %s from %s",
            note.note_type_label,
            self.student_display_name,
            note.teacher,
        )
        self.hass.bus.async_fire(EVENT_NEW_NOTE, payload)

