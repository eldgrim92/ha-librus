"""Unit tests for LibrusDataUpdateCoordinator diffing, persistence, and Event Bus triggers."""

from __future__ import annotations

from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import install_ha_stubs

install_ha_stubs()

from homeassistant.config_entries import ConfigEntry  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers.storage import Store  # noqa: E402

from custom_components.librus.api import (  # noqa: E402
    LibrusDataSnapshot,
    LibrusGrade,
    LibrusMessage,
    LibrusNote,
    StudentProfile,
)
from custom_components.librus.const import (  # noqa: E402
    CONF_STUDENT_NAME,
    CONF_SYNC_INTERVAL,
    EVENT_NEW_GRADE,
    EVENT_NEW_MESSAGE,
    EVENT_NEW_NOTE,
)
from custom_components.librus.coordinator import LibrusDataUpdateCoordinator  # noqa: E402


class TestLibrusCoordinator(unittest.IsolatedAsyncioTestCase):
    """Test suite for coordinator baseline seeding, delta detection, and HA Event Bus firing."""

    def setUp(self) -> None:
        Store._shared_memory.clear()
        self.hass = HomeAssistant()
        self.entry = ConfigEntry(
            entry_id="kid_jan_1",
            title="Librus - Jan Kowalski",
            data={CONF_STUDENT_NAME: "Jan Kowalski"},
            options={CONF_SYNC_INTERVAL: 20},
        )
        self.mock_client = MagicMock()
        self.mock_client.max_items = 10

    async def test_initial_refresh_seeds_state_without_firing_events(self) -> None:
        initial_snapshot = LibrusDataSnapshot(
            student=StudentProfile(account_id="101", student_name="Jan Kowalski"),
            messages=[
                LibrusMessage(
                    message_id="m1",
                    sender="Anna Nowak",
                    subject="Powitanie",
                    sent_at="2026-09-01",
                    is_unread=False,
                    body_text="Witamy w nowym roku szkolnym",
                )
            ],
            grades=[
                LibrusGrade(
                    grade_id="g1",
                    subject="Matematyka",
                    value="5",
                    date="2026-09-05",
                )
            ],
            notes=[
                LibrusNote(
                    note_id="n1",
                    teacher="Anna Nowak",
                    category="Pochwała",
                    content="Pomoc koleżeńska",
                    date="2026-09-06",
                    positive=True,
                )
            ],
        )
        self.mock_client.async_fetch_snapshot = AsyncMock(return_value=initial_snapshot)

        coordinator = LibrusDataUpdateCoordinator(
            hass=self.hass,
            entry=self.entry,
            client=self.mock_client,
        )
        self.assertEqual(coordinator.update_interval, timedelta(minutes=20))

        await coordinator.async_refresh()
        self.assertEqual(len(self.hass.bus.fired_events), 0)

        # Second poll with new message, new grade, and new note
        second_snapshot = LibrusDataSnapshot(
            student=StudentProfile(account_id="101", student_name="Jan Kowalski"),
            messages=[
                LibrusMessage(
                    message_id="m2",
                    sender="Piotr Wiśniewski (Nauczyciel)",
                    subject="Sprawdzian z ułamków",
                    sent_at="2026-10-31 12:00",
                    is_unread=True,
                    body_markdown="### 📩 Sprawdzian z ułamków\n\nW przyszły wtorek.",
                    body_text="W przyszły wtorek.",
                ),
                initial_snapshot.messages[0],
            ],
            grades=[
                LibrusGrade(
                    grade_id="g2",
                    subject="Fizyka",
                    value="5+",
                    weight=3,
                    category="Kartkówka",
                    teacher="Marek Zieliński",
                    date="2026-10-31",
                    comment="Bardzo dobrze",
                ),
                initial_snapshot.grades[0],
            ],
            notes=[
                LibrusNote(
                    note_id="n2",
                    teacher="Marek Zieliński",
                    category="Uwaga",
                    content="Brak zeszytu",
                    date="2026-10-31",
                    positive=False,
                ),
                initial_snapshot.notes[0],
            ],
        )
        self.mock_client.async_fetch_snapshot = AsyncMock(return_value=second_snapshot)

        await coordinator.async_refresh()

        self.assertEqual(len(self.hass.bus.fired_events), 3)
        event_types = [ev[0] for ev in self.hass.bus.fired_events]
        self.assertEqual(
            event_types,
            [EVENT_NEW_MESSAGE, EVENT_NEW_GRADE, EVENT_NEW_NOTE],
        )

        msg_payload = self.hass.bus.fired_events[0][1]
        self.assertEqual(msg_payload["student_name"], "Jan Kowalski")
        self.assertEqual(msg_payload["message_id"], "m2")
        self.assertEqual(msg_payload["subject"], "Sprawdzian z ułamków")
        self.assertEqual(msg_payload["body_text"], "W przyszły wtorek.")

        grade_payload = self.hass.bus.fired_events[1][1]
        self.assertEqual(grade_payload["grade"], "5+")
        self.assertEqual(grade_payload["subject"], "Fizyka")
        self.assertEqual(grade_payload["comment"], "Bardzo dobrze")

        note_payload = self.hass.bus.fired_events[2][1]
        self.assertEqual(note_payload["note_id"], "n2")
        self.assertEqual(note_payload["type"], "Negatywna")
        self.assertEqual(note_payload["content"], "Brak zeszytu")

        # Third poll with identical data should fire 0 new events
        self.hass.bus.fired_events.clear()
        await coordinator.async_refresh()
        self.assertEqual(len(self.hass.bus.fired_events), 0)

    async def test_update_options_changes_sync_period_dynamically(self) -> None:
        coordinator = LibrusDataUpdateCoordinator(
            hass=self.hass,
            entry=self.entry,
            client=self.mock_client,
        )
        coordinator.update_options(sync_interval_minutes=45, max_items=30)
        self.assertEqual(coordinator.update_interval, timedelta(minutes=45))
        self.assertEqual(self.mock_client.max_items, 30)


if __name__ == "__main__":
    unittest.main()

