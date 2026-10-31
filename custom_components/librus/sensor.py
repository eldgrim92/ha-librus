"""Sensor platform for Librus Synergia (messages, grades, notes, lucky number)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LibrusDataUpdateCoordinator
from .entity import LibrusEntity

_MAX_STATE_LEN = 250


def _truncate_state(value: str) -> str:
    """Ensure sensor state string never exceeds Home Assistant's 255-char limit."""
    if len(value) <= _MAX_STATE_LEN:
        return value
    return value[: _MAX_STATE_LEN - 1].rstrip() + "…"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Librus sensors for a child's config entry."""
    coordinator: LibrusDataUpdateCoordinator = getattr(
        entry, "runtime_data", None
    ) or hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        LibrusUnreadMessagesSensor(coordinator),
        LibrusLatestMessageSensor(coordinator),
        LibrusLatestGradeSensor(coordinator),
        LibrusNotesSensor(coordinator),
        LibrusLuckyNumberSensor(coordinator),
    ]
    async_add_entities(entities)


class LibrusUnreadMessagesSensor(LibrusEntity, SensorEntity):
    """Sensor showing unread messages count and a formatted inbox feed in attributes."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "wiadomości"

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize unread messages sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_key="unread_messages",
            name="Nieprzeczytane wiadomości",
            icon="mdi:email-mark-as-unread",
        )

    @property
    def native_value(self) -> int:
        """Return the number of unread incoming messages."""
        if not self.coordinator.data:
            return 0
        return self.coordinator.data.unread_messages_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return readable message feed and latest message metadata."""
        if not self.coordinator.data:
            return {}

        messages = self.coordinator.data.messages
        latest = self.coordinator.data.latest_message
        inbox_markdown_blocks = [msg.body_markdown for msg in messages]

        return {
            "student_name": self.coordinator.student_display_name,
            "total_fetched": len(messages),
            "latest_sender": latest.sender if latest else None,
            "latest_subject": latest.subject if latest else None,
            "latest_sent_at": latest.sent_at if latest else None,
            "latest_body_markdown": latest.body_markdown if latest else None,
            "inbox_markdown": "\n\n===\n\n".join(inbox_markdown_blocks),
            "recent_messages": [msg.to_attribute_dict() for msg in messages],
        }


class LibrusLatestMessageSensor(LibrusEntity, SensorEntity):
    """Sensor presenting the latest incoming message in a clean, readable form."""

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize latest message sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_key="latest_message",
            name="Ostatnia wiadomość",
            icon="mdi:email-open-outline",
        )

    @property
    def native_value(self) -> str:
        """Return a concise summary of the latest message ('Subject — Sender')."""
        if not self.coordinator.data or not self.coordinator.data.latest_message:
            return "Brak wiadomości"

        latest = self.coordinator.data.latest_message
        return _truncate_state(f"{latest.subject} — {latest.sender}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full readable Markdown and plain text body of the latest message."""
        if not self.coordinator.data or not self.coordinator.data.latest_message:
            return {"student_name": self.coordinator.student_display_name}

        latest = self.coordinator.data.latest_message
        return {
            "student_name": self.coordinator.student_display_name,
            **latest.to_attribute_dict(),
        }


class LibrusLatestGradeSensor(LibrusEntity, SensorEntity):
    """Sensor presenting the latest school grade and recent grades list."""

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize latest grade sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_key="latest_grade",
            name="Ostatnia ocena",
            icon="mdi:school-outline",
        )

    @property
    def native_value(self) -> str:
        """Return the latest grade value and subject (e.g., '5 (Matematyka)')."""
        if not self.coordinator.data or not self.coordinator.data.latest_grade:
            return "Brak ocen"

        latest = self.coordinator.data.latest_grade
        return _truncate_state(f"{latest.value} ({latest.subject})")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed attributes for the latest grade and recent grades history."""
        if not self.coordinator.data:
            return {}

        grades = self.coordinator.data.grades
        latest = self.coordinator.data.latest_grade

        attrs: dict[str, Any] = {
            "student_name": self.coordinator.student_display_name,
            "total_recent_grades": len(grades),
            "recent_grades": [g.to_attribute_dict() for g in grades],
        }
        if latest:
            attrs.update(latest.to_attribute_dict())
        return attrs


class LibrusNotesSensor(LibrusEntity, SensorEntity):
    """Sensor presenting behavior notes (Uwagi / Pochwały) for the student."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "uwag"

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize notes sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_key="notes",
            name="Uwagi i pochwały",
            icon="mdi:notebook-edit-outline",
        )

    @property
    def native_value(self) -> int:
        """Return total number of recent behavior notes."""
        if not self.coordinator.data:
            return 0
        return len(self.coordinator.data.notes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return latest note details and list of all recent notes."""
        if not self.coordinator.data:
            return {}

        notes = self.coordinator.data.notes
        latest = self.coordinator.data.latest_note
        positive_count = sum(1 for n in notes if n.positive is True)
        negative_count = sum(1 for n in notes if n.positive is False)

        return {
            "student_name": self.coordinator.student_display_name,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "latest_teacher": latest.teacher if latest else None,
            "latest_category": latest.category if latest else None,
            "latest_type": latest.note_type_label if latest else None,
            "latest_date": latest.date if latest else None,
            "latest_content": latest.content if latest else None,
            "recent_notes": [n.to_attribute_dict() for n in notes],
        }


class LibrusLuckyNumberSensor(LibrusEntity, SensorEntity):
    """Sensor showing today's lucky number (Szczęśliwy numerek) for the child's school."""

    def __init__(self, coordinator: LibrusDataUpdateCoordinator) -> None:
        """Initialize lucky number sensor."""
        super().__init__(
            coordinator=coordinator,
            entity_key="lucky_number",
            name="Szczęśliwy numerek",
            icon="mdi:clover",
        )

    @property
    def native_value(self) -> int | None:
        """Return today's lucky number."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.student.lucky_number

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return lucky number date and whether it matches the student's number."""
        if not self.coordinator.data:
            return {}

        student = self.coordinator.data.student
        return {
            "student_name": self.coordinator.student_display_name,
            "lucky_number_date": student.lucky_number_date,
            "student_number": student.student_number,
            "is_lucky_today": student.is_lucky_today,
        }

