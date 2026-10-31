"""Data models for the Librus Synergia Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class StudentProfile:
    """Represents a child/student profile on Librus Synergia."""

    account_id: str
    student_name: str
    class_name: str = ""
    student_number: int | None = None
    lucky_number: int | None = None
    lucky_number_date: str | None = None

    @property
    def is_lucky_today(self) -> bool:
        """Return True if the student's journal number matches today's lucky number."""
        if self.student_number is None or self.lucky_number is None:
            return False
        return self.student_number == self.lucky_number


@dataclass(slots=True)
class LibrusMessage:
    """Represents an incoming message from Librus Wiadomości in readable formats."""

    message_id: str
    sender: str
    subject: str
    sent_at: str
    is_unread: bool
    body_html: str = ""
    body_markdown: str = ""
    body_text: str = ""
    has_attachments: bool = False
    attachments: list[str] = field(default_factory=list)
    url: str = ""

    def to_attribute_dict(self) -> dict[str, Any]:
        """Serialize message into a dictionary suitable for HA entity attributes and events."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "subject": self.subject,
            "sent_at": self.sent_at,
            "unread": self.is_unread,
            "body_markdown": self.body_markdown,
            "body_text": self.body_text,
            "has_attachments": self.has_attachments,
            "attachments": self.attachments,
        }


@dataclass(slots=True)
class LibrusGrade:
    """Represents a school grade in Librus Synergia."""

    grade_id: str
    subject: str
    value: str
    date: str
    added_at: str = ""
    weight: int | float | None = None
    category: str = ""
    teacher: str = ""
    comment: str = ""
    semester: int | None = None
    is_final: bool = False
    counts_to_average: bool = True

    def to_attribute_dict(self) -> dict[str, Any]:
        """Serialize grade into a dictionary suitable for HA entity attributes and events."""
        return {
            "grade_id": self.grade_id,
            "subject": self.subject,
            "grade": self.value,
            "weight": self.weight,
            "category": self.category,
            "teacher": self.teacher,
            "date": self.date,
            "added_at": self.added_at,
            "comment": self.comment,
            "semester": self.semester,
            "is_final": self.is_final,
        }


@dataclass(slots=True)
class LibrusNote:
    """Represents a behavior note (Uwaga / Pochwała) in Librus Synergia."""

    note_id: str
    teacher: str
    category: str
    content: str
    date: str
    positive: bool | None = None

    @property
    def note_type_label(self) -> str:
        """Return human-readable note type."""
        if self.positive is True:
            return "Pozytywna"
        if self.positive is False:
            return "Negatywna"
        return self.category or "Neutralna"

    def to_attribute_dict(self) -> dict[str, Any]:
        """Serialize note into a dictionary suitable for HA entity attributes and events."""
        return {
            "note_id": self.note_id,
            "type": self.note_type_label,
            "positive": self.positive,
            "category": self.category,
            "teacher": self.teacher,
            "date": self.date,
            "content": self.content,
        }


@dataclass(slots=True)
class LibrusDataSnapshot:
    """Complete snapshot of a student's Librus data returned by the coordinator."""

    student: StudentProfile
    messages: list[LibrusMessage] = field(default_factory=list)
    grades: list[LibrusGrade] = field(default_factory=list)
    notes: list[LibrusNote] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)

    @property
    def unread_messages_count(self) -> int:
        """Count of unread incoming messages."""
        return sum(1 for msg in self.messages if msg.is_unread)

    @property
    def latest_message(self) -> LibrusMessage | None:
        """Return the most recent message, if any."""
        return self.messages[0] if self.messages else None

    @property
    def latest_grade(self) -> LibrusGrade | None:
        """Return the most recent grade, if any."""
        return self.grades[0] if self.grades else None

    @property
    def latest_note(self) -> LibrusNote | None:
        """Return the most recent note, if any."""
        return self.notes[0] if self.notes else None

