"""Constants for the Librus Synergia Home Assistant integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "librus"
MANUFACTURER: Final = "Librus Sp. z o.o."
MODEL_STUDENT_ACCOUNT: Final = "Konto Ucznia / Rodzica (Synergia)"

# Configuration & Options keys
CONF_STUDENT_NAME: Final = "student_name"
CONF_SYNC_INTERVAL: Final = "sync_interval"
CONF_MAX_ITEMS: Final = "max_items"

# Defaults & Limits
DEFAULT_SYNC_INTERVAL_MINUTES: Final = 30
MIN_SYNC_INTERVAL_MINUTES: Final = 5
MAX_SYNC_INTERVAL_MINUTES: Final = 360

DEFAULT_MAX_ITEMS: Final = 10
MIN_MAX_ITEMS: Final = 3
MAX_MAX_ITEMS: Final = 50

# Home Assistant Event Bus names for push notifications
EVENT_NEW_MESSAGE: Final = f"{DOMAIN}_new_message"
EVENT_NEW_GRADE: Final = f"{DOMAIN}_new_grade"
EVENT_NEW_NOTE: Final = f"{DOMAIN}_new_note"

# Services
SERVICE_REFRESH: Final = "refresh"

# Storage configuration for diffing seen IDs across HA restarts
STORAGE_VERSION: Final = 1
STORAGE_KEY_PREFIX: Final = f"{DOMAIN}_seen_state"

# Librus OAuth & Synergia Endpoints (matching Mati365/librus-api)
LIBRUS_SYNERGIA_URL: Final = "https://synergia.librus.pl"
LIBRUS_PORTAL_RODZINA_LOGIN_URL: Final = "https://synergia.librus.pl/loguj/portalRodzina"
LIBRUS_OAUTH_AUTH_URL: Final = (
    "https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata"
)
LIBRUS_OAUTH_LOGIN_URL: Final = "https://api.librus.pl/OAuth/Authorization?client_id=46"
LIBRUS_OAUTH_GRANT_URL: Final = "https://api.librus.pl/OAuth/Authorization/Grant?client_id=46"
LIBRUS_OAUTH_2FA_URL: Final = "https://api.librus.pl/OAuth/Authorization/2FA?client_id=46"
LIBRUS_API_BASE_URL: Final = "https://synergia.librus.pl/gateway/api/2.0"
LIBRUS_API_TOKEN_INFO_URL: Final = "https://synergia.librus.pl/gateway/api/2.0/Auth/TokenInfo"
LIBRUS_API_USER_INFO_URL: Final = "https://synergia.librus.pl/gateway/api/2.0/Auth/UserInfo"

# Librus Synergia Web Endpoints (used by Mati365/librus-api modules)
LIBRUS_SYNERGIA_INDEX_URL: Final = "https://synergia.librus.pl/uczen/index"
LIBRUS_SYNERGIA_INFO_URL: Final = "https://synergia.librus.pl/informacje"
LIBRUS_SYNERGIA_GRADES_URL: Final = "https://synergia.librus.pl/przegladaj_oceny/uczen"
LIBRUS_SYNERGIA_NOTES_URL: Final = "https://synergia.librus.pl/uwagi"
LIBRUS_SYNERGIA_MESSAGES_URL: Final = "https://synergia.librus.pl/wiadomosci"

