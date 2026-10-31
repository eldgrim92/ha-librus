"""Librus Synergia API and message readability engine."""

from .client import (
    LibrusApiClient,
    LibrusApiError,
    LibrusAuthError,
    LibrusConnectionError,
)
from .models import (
    LibrusDataSnapshot,
    LibrusGrade,
    LibrusMessage,
    LibrusNote,
    StudentProfile,
)
from .parser import (
    format_message_markdown,
    format_sender_name,
    html_to_clean_markdown,
    html_to_plain_text,
)

__all__ = [
    "LibrusApiClient",
    "LibrusApiError",
    "LibrusAuthError",
    "LibrusConnectionError",
    "LibrusDataSnapshot",
    "LibrusGrade",
    "LibrusMessage",
    "LibrusNote",
    "StudentProfile",
    "format_message_markdown",
    "format_sender_name",
    "html_to_clean_markdown",
    "html_to_plain_text",
]

