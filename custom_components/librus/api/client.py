"""Async Librus Synergia & Wiadomości API client.

Implements the authorization and session flow from `Mati365/librus-api`:
1. GET `https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata`
   (or via `https://synergia.librus.pl/loguj/portalRodzina`) to initialize `oauth_state` cookies.
2. POST credentials (`action=login`, `login=...`, `pass=...`) to
   `https://api.librus.pl/OAuth/Authorization?client_id=46`.
3. Follow `goTo` / `https://api.librus.pl/OAuth/Authorization/Grant?client_id=46` (and `/2FA?client_id=46`)
   which redirects to `synergia.librus.pl` and establishes `DZIENNIKSID` / `SDZIENNIKSID` cookies.
4. Activate the API Gateway session via `Auth/TokenInfo` and `Auth/UserInfo {identifier}` if needed,
   and support both the JSON gateway (`gateway/api/2.0/...`) and HTML scraping (`Mati365/librus-api`
   endpoints: `/informacje`, `/przegladaj_oceny/uczen`, `/uwagi`, `/wiadomosci`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import logging
import re
import time
from typing import Any

try:
    import aiohttp
except ImportError:  # pragma: no cover - fallback for test environments without aiohttp
    aiohttp = None  # type: ignore[assignment]

from ..const import (
    DEFAULT_MAX_ITEMS,
    LIBRUS_API_BASE_URL,
    LIBRUS_API_TOKEN_INFO_URL,
    LIBRUS_API_USER_INFO_URL,
    LIBRUS_OAUTH_2FA_URL,
    LIBRUS_OAUTH_AUTH_URL,
    LIBRUS_OAUTH_GRANT_URL,
    LIBRUS_OAUTH_LOGIN_URL,
    LIBRUS_PORTAL_RODZINA_LOGIN_URL,
    LIBRUS_SYNERGIA_GRADES_URL,
    LIBRUS_SYNERGIA_INFO_URL,
    LIBRUS_SYNERGIA_MESSAGES_URL,
    LIBRUS_SYNERGIA_NOTES_URL,
    LIBRUS_SYNERGIA_URL,
)
from .models import (
    LibrusDataSnapshot,
    LibrusGrade,
    LibrusMessage,
    LibrusNote,
    StudentProfile,
)
from .parser import (
    _DOMNode,
    _find_all_nodes,
    _parse_html_tree,
    format_message_markdown,
    format_sender_name,
    html_to_plain_text,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, text/html, */*; q=0.01",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

_MESSAGE_ID_RE = re.compile(r"/wiadomosci/\d+/\d+/(\d+)")
_GRADE_ID_RE = re.compile(r"/pokaz_lekcje/(\d+)|ocena[_-]?(\d+)")
_KV_TITLE_RE = re.compile(r"([^:\n]+):\s*([^\n<]+)")

_NETWORK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    (aiohttp.ClientError, asyncio.TimeoutError, OSError)
    if aiohttp is not None
    else (asyncio.TimeoutError, OSError)
)


class LibrusApiError(Exception):
    """Base exception for Librus API errors."""


class LibrusAuthError(LibrusApiError):
    """Raised when credentials are invalid or authentication is rejected."""


class LibrusConnectionError(LibrusApiError):
    """Raised when network communication with Librus fails."""


class LibrusApiClient:
    """Async client for Librus Synergia using the `Mati365/librus-api` authorization approach."""

    def __init__(
        self,
        username: str,
        password: str,
        session: Any = None,
        max_items: int = DEFAULT_MAX_ITEMS,
    ) -> None:
        """Initialize the Librus client."""
        self._username = username.strip()
        self._password = password
        self._external_session = session
        self._internal_session: Any = None
        self._cookie_jar = aiohttp.CookieJar(unsafe=True) if aiohttp else None
        self._authenticated = False
        self._gateway_available = True
        self._max_items = max_items
        self._lock = asyncio.Lock()

        # Caches for JSON gateway lookup tables (subjects, categories, users/teachers)
        self._subjects_cache: dict[int, str] = {}
        self._grade_categories_cache: dict[int, tuple[str, int | float | None]] = {}
        self._note_categories_cache: dict[int, tuple[str, bool | None]] = {}
        self._users_cache: dict[int, str] = {}

    @property
    def max_items(self) -> int:
        """Return maximum number of recent items to fetch/expose."""
        return self._max_items

    @max_items.setter
    def max_items(self, value: int) -> None:
        """Update maximum number of recent items."""
        self._max_items = max(1, value)

    async def _get_session(self) -> Any:
        """Return an active aiohttp ClientSession with an isolated cookie jar per account."""
        if self._external_session is not None:
            return self._external_session
        if aiohttp is None:
            raise LibrusConnectionError("aiohttp is required for live HTTP requests")
        if self._internal_session is None or self._internal_session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._internal_session = aiohttp.ClientSession(
                cookie_jar=self._cookie_jar,
                headers=_DEFAULT_HEADERS,
                timeout=timeout,
            )
        return self._internal_session

    async def async_close(self) -> None:
        """Close the internal HTTP session if created."""
        if self._internal_session and not self._internal_session.closed:
            await self._internal_session.close()
            self._internal_session = None

    async def async_authenticate(self) -> None:
        """Authorize with Librus Synergia using the `Mati365/librus-api` `authorize()` workflow.

        Steps:
        1. `GET https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata`
           to initialize the OAuth session and cookies (`oauth_state`).
        2. `POST https://api.librus.pl/OAuth/Authorization?client_id=46` with form data:
           `action=login`, `login=<username>`, `pass=<password>`.
        3. Follow the grant step:
           - If the login response provides a `goTo` path (e.g. `/OAuth/Authorization/Grant?client_id=46`
             or `/OAuth/Authorization/2FA?client_id=46`), follow `https://api.librus.pl{goTo}`.
           - Also ensure `https://api.librus.pl/OAuth/Authorization/Grant?client_id=46` is completed
             so the redirect to `synergia.librus.pl` sets `DZIENNIKSID` / `SDZIENNIKSID` cookies.
        4. Activate the Synergia API Gateway session (`Auth/TokenInfo` -> `Auth/UserInfo/{identifier}`)
           when available.
        """
        session = await self._get_session()
        if self._cookie_jar is not None:
            self._cookie_jar.clear()

        try:
            # Step 1A: Bootstrap session on synergia.librus.pl/loguj/portalRodzina?v=<timestamp>
            portal_url = f"{LIBRUS_PORTAL_RODZINA_LOGIN_URL}?v={int(time.time())}"
            async with session.get(
                portal_url,
                allow_redirects=True,
            ) as portal_resp:
                final_init_url = str(getattr(portal_resp, "url", ""))

            # Step 1B: Ensure OAuth authorization cookie is initialized if portal_url didn't redirect there
                if "api.librus.pl/OAuth/Authorization" not in final_init_url:
                    async with session.get(
                        LIBRUS_OAUTH_AUTH_URL,
                        allow_redirects=True,
                    ) as resp:
                        if resp.status >= 500:
                            err_body = await self._safe_response_text(resp)
                            _LOGGER.error(
                                "Librus OAuth init HTTP %s from %s. Response body: %s",
                                resp.status,
                                LIBRUS_OAUTH_AUTH_URL,
                                err_body,
                            )
                            raise LibrusConnectionError(
                                f"Librus OAuth server error during initialization: HTTP {resp.status} ({err_body[:300]})"
                            )

            # Step 2: Submit credentials via form-urlencoded POST
            form_payload = {
                "action": "login",
                "login": self._username,
                "pass": self._password,
            }
            login_headers = {
                "Referer": LIBRUS_OAUTH_AUTH_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
            async with session.post(
                LIBRUS_OAUTH_LOGIN_URL,
                data=form_payload,
                headers=login_headers,
            ) as resp:
                if resp.status in (401, 403) or resp.status >= 400:
                    err_body = await self._safe_response_text(resp)
                    _LOGGER.error(
                        "Librus OAuth login failed with HTTP %s from %s. Response body: %s",
                        resp.status,
                        LIBRUS_OAUTH_LOGIN_URL,
                        err_body,
                    )
                    if resp.status in (401, 403):
                        raise LibrusAuthError(
                            f"Invalid Librus username or password (HTTP {resp.status}: {err_body[:300]})"
                        )

                data = await self._safe_json(resp)
                if isinstance(data, dict):
                    status = data.get("status")
                    if status == "error" or data.get("errors"):
                        _LOGGER.error(
                            "Librus OAuth login returned error payload for %s: %s",
                            self._username,
                            data,
                        )
                        raise LibrusAuthError(
                            f"Invalid Librus username or password: {data}"
                        )
                    go_to = data.get("goTo")
                else:
                    raw_login_text = await self._safe_response_text(resp)
                    _LOGGER.warning(
                        "Librus OAuth login returned non-JSON response (HTTP %s): %s",
                        resp.status,
                        raw_login_text[:500],
                    )
                    go_to = None

            # Step 3: Complete Grant / 2FA redirect as in Mati365/librus-api
            # Mati365/librus-api calls `GET https://api.librus.pl/OAuth/Authorization/Grant?client_id=46`
            # (or follows `goTo` from the JSON response) to exchange the OAuth code and set Synergia cookies.
            grant_targets: list[str] = []
            if go_to:
                resolved_goto = (
                    f"https://api.librus.pl{go_to}"
                    if go_to.startswith("/")
                    else go_to
                )
                grant_targets.append(resolved_goto)

            if LIBRUS_OAUTH_GRANT_URL not in grant_targets:
                grant_targets.append(LIBRUS_OAUTH_GRANT_URL)

            grant_succeeded = False
            for target_url in grant_targets:
                async with session.get(target_url, allow_redirects=True) as grant_resp:
                    if grant_resp.status in (401, 403):
                        err_body = await self._safe_response_text(grant_resp)
                        _LOGGER.error(
                            "Librus OAuth Grant failed with HTTP %s at %s. Response body: %s",
                            grant_resp.status,
                            target_url,
                            err_body,
                        )
                        raise LibrusAuthError(
                            f"Failed to finalize Librus OAuth Grant (HTTP {grant_resp.status}: {err_body[:300]})"
                        )
                    if grant_resp.status >= 400:
                        err_body = await self._safe_response_text(grant_resp)
                        _LOGGER.warning(
                            "Librus OAuth Grant returned HTTP %s at %s. Response body: %s",
                            grant_resp.status,
                            target_url,
                            err_body,
                        )
                    if grant_resp.status < 400:
                        grant_succeeded = True
                        # If we landed on api.librus.pl/OAuth/Authorization/2FA and it returned JSON with goTo
                        grant_json = await self._safe_json(grant_resp)
                        if isinstance(grant_json, dict) and grant_json.get("goTo"):
                            next_goto = str(grant_json["goTo"])
                            next_url = (
                                f"https://api.librus.pl{next_goto}"
                                if next_goto.startswith("/")
                                else next_goto
                            )
                            async with session.get(next_url, allow_redirects=True) as next_resp:
                                if next_resp.status >= 400:
                                    err_body = await self._safe_response_text(next_resp)
                                    _LOGGER.error(
                                        "Librus secondary goTo failed with HTTP %s at %s. Response: %s",
                                        next_resp.status,
                                        next_url,
                                        err_body,
                                    )
                        break

            if not grant_succeeded:
                # Fallback to 2FA endpoint if Grant endpoint wasn't reachable directly
                async with session.get(LIBRUS_OAUTH_2FA_URL, allow_redirects=True) as resp_2fa:
                    if resp_2fa.status >= 400:
                        err_body = await self._safe_response_text(resp_2fa)
                        _LOGGER.error(
                            "Librus 2FA fallback failed with HTTP %s at %s. Response body: %s",
                            resp_2fa.status,
                            LIBRUS_OAUTH_2FA_URL,
                            err_body,
                        )
                        raise LibrusAuthError(
                            f"Failed to establish Librus Synergia session (HTTP {resp_2fa.status}: {err_body[:300]})"
                        )

            # Step 4: Activate API Gateway token if supported (Auth/TokenInfo -> Auth/UserInfo)
            await self._async_activate_api_gateway(session)

            self._authenticated = True
        except LibrusApiError:
            raise
        except _NETWORK_EXCEPTIONS as err:
            raise LibrusConnectionError(
                f"Network error connecting to Librus: {err}"
            ) from err

    async def _async_activate_api_gateway(self, session: Any) -> None:
        """Activate `synergia.librus.pl/gateway/api/2.0` session if available."""
        try:
            async with session.get(LIBRUS_API_TOKEN_INFO_URL) as token_resp:
                if token_resp.status != 200:
                    return
                token_data = await self._safe_json(token_resp)
                identifier = (token_data or {}).get("UserIdentifier")
                if identifier:
                    async with session.get(f"{LIBRUS_API_USER_INFO_URL}/{identifier}"):
                        pass
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Optional gateway TokenInfo activation skipped")

    async def _api_get(self, endpoint: str, retry_auth: bool = True) -> dict[str, Any]:
        """Perform an authenticated GET request to Librus Synergia JSON API."""
        if not self._authenticated:
            await self.async_authenticate()

        session = await self._get_session()
        url = f"{LIBRUS_API_BASE_URL}/{endpoint.lstrip('/')}"

        try:
            async with session.get(url) as resp:
                if resp.status in (401, 403) and retry_auth:
                    _LOGGER.debug(
                        "Librus session expired, re-authenticating for %s",
                        self._username,
                    )
                    self._authenticated = False
                    await self.async_authenticate()
                    return await self._api_get(endpoint, retry_auth=False)

                if resp.status in (401, 403):
                    err_body = await self._safe_response_text(resp)
                    _LOGGER.error(
                        "Librus API unauthorized (HTTP %s) at %s. Response body: %s",
                        resp.status,
                        url,
                        err_body,
                    )
                    raise LibrusAuthError(
                        f"Unauthorized access to {endpoint} (HTTP {resp.status}: {err_body[:300]})"
                    )

                if resp.status >= 400:
                    err_body = await self._safe_response_text(resp)
                    _LOGGER.error(
                        "Librus API HTTP %s at %s. Response body: %s",
                        resp.status,
                        url,
                        err_body,
                    )
                    raise LibrusApiError(
                        f"HTTP {resp.status} from {endpoint}: {err_body[:300]}"
                    )

                data = await self._safe_json(resp)
                return data if isinstance(data, dict) else {}
        except LibrusApiError:
            raise
        except _NETWORK_EXCEPTIONS as err:
            raise LibrusConnectionError(
                f"Communication error calling {endpoint}: {err}"
            ) from err

    async def _synergia_html_get(self, url: str, retry_auth: bool = True) -> str:
        """Perform an authenticated GET request to a Synergia HTML page (like `Mati365/librus-api` `_request`)."""
        if not self._authenticated:
            await self.async_authenticate()

        session = await self._get_session()
        full_url = f"{LIBRUS_SYNERGIA_URL}/{url.lstrip('/')}" if not url.startswith("http") else url

        try:
            async with session.get(full_url, allow_redirects=True) as resp:
                text = await resp.text()
                # Check if redirected back to login screen
                if (
                    resp.status in (401, 403)
                    or "loguj" in str(resp.url).lower()
                    or "Brak dostępu" in text
                ) and retry_auth:
                    self._authenticated = False
                    await self.async_authenticate()
                    return await self._synergia_html_get(url, retry_auth=False)

                if resp.status >= 400:
                    _LOGGER.error(
                        "Librus Synergia HTML GET failed with HTTP %s at %s (final URL: %s). Response body: %s",
                        resp.status,
                        full_url,
                        getattr(resp, "url", full_url),
                        text[:500],
                    )
                    raise LibrusApiError(
                        f"HTTP {resp.status} fetching {full_url}: {text[:300]}"
                    )

                return text
        except LibrusApiError:
            raise
        except _NETWORK_EXCEPTIONS as err:
            raise LibrusConnectionError(
                f"Communication error fetching {full_url}: {err}"
            ) from err

    @staticmethod
    async def _safe_response_text(resp: Any) -> str:
        """Attempt to read response text safely for error diagnostics."""
        try:
            text = await resp.text()
            return " ".join(str(text).split())
        except Exception:  # noqa: BLE001
            return "<unreadable response body>"

    @staticmethod
    async def _safe_json(resp: Any) -> dict[str, Any] | None:
        """Attempt to decode JSON response safely."""
        try:
            return await resp.json(content_type=None)
        except Exception:  # noqa: BLE001
            return None

    async def async_get_student_profile(self) -> StudentProfile:
        """Fetch student profile, class info, and today's lucky number.

        Tries the JSON Gateway (`Me`, `Classes`, `LuckyNumbers`) first, and falls back
        to scraping `/informacje` (matching `Mati365/librus-api` `info.getAccountInfo()`).
        """
        try:
            me_data = await self._api_get("Me")
            me_obj = me_data.get("Me", {})
            account = me_obj.get("Account", {})
            user = me_obj.get("User", {})

            first_name = user.get("FirstName") or account.get("FirstName") or ""
            last_name = user.get("LastName") or account.get("LastName") or ""
            student_name = f"{first_name} {last_name}".strip()
            if student_name:
                account_id = str(account.get("Id") or user.get("Id") or self._username)
                class_name = ""
                try:
                    class_data = await self._api_get("Classes")
                    cls_obj = class_data.get("Class", {})
                    number = cls_obj.get("Number")
                    symbol = cls_obj.get("Symbol", "")
                    if number or symbol:
                        class_name = f"{number or ''}{symbol}".strip()
                except LibrusApiError:
                    pass

                lucky_number: int | None = None
                lucky_date: str | None = None
                try:
                    lucky_data = await self._api_get("LuckyNumbers")
                    lucky_obj = lucky_data.get("LuckyNumber", {})
                    if lucky_obj.get("LuckyNumber") is not None:
                        lucky_number = int(lucky_obj["LuckyNumber"])
                    lucky_date = lucky_obj.get("LuckyNumberDay")
                except (LibrusApiError, ValueError, TypeError):
                    pass

                return StudentProfile(
                    account_id=account_id,
                    student_name=student_name,
                    class_name=class_name,
                    lucky_number=lucky_number,
                    lucky_number_date=lucky_date,
                )
        except LibrusAuthError:
            raise
        except LibrusApiError:
            _LOGGER.debug("Falling back to HTML /informacje for %s", self._username)

        # Fallback: scrape `/informacje` exactly like `Mati365/librus-api` `info.getAccountInfo()`
        info_html = await self._synergia_html_get(LIBRUS_SYNERGIA_INFO_URL)
        return self.parse_account_info_html(info_html, default_username=self._username)

    @staticmethod
    def parse_account_info_html(
        info_html: str,
        default_username: str = "",
    ) -> StudentProfile:
        """Parse `/informacje` HTML page (as in `Mati365/librus-api` `info.getAccountInfo()`)."""
        root = _parse_html_tree(info_html)
        student_name = ""
        class_name = ""
        student_number: int | None = None
        lucky_number: int | None = None

        # Look for lucky number span: <span class="luckyNumber"><b>14</b></span>
        for node in _find_all_nodes(root, {"span", "b", "div"}, recursive=True):
            cls_attr = node.attrs.get("class", "")
            if "luckynumber" in cls_attr.lower():
                txt = node.get_text(" ", strip=True)
                num_match = re.search(r"\b(\d{1,2})\b", txt)
                if num_match:
                    lucky_number = int(num_match.group(1))
                    break

        # Parse table rows in `/informacje` (`Imię i nazwisko ucznia`, `Klasa`, `Nr w dzienniku`)
        for tr in _find_all_nodes(root, {"tr"}, recursive=True):
            th_nodes = _find_all_nodes(tr, {"th", "td"}, recursive=False)
            if len(th_nodes) < 2:
                continue
            label = th_nodes[0].get_text(" ", strip=True).lower()
            val = th_nodes[1].get_text(" ", strip=True)
            if "imię i nazwisko" in label and val:
                student_name = val
            elif label.startswith("klasa") and val:
                class_name = val
            elif ("nr w dzienniku" in label or "numer w dzienniku" in label) and val.isdigit():
                student_number = int(val)

        return StudentProfile(
            account_id=default_username or student_name or "student",
            student_name=student_name or default_username,
            class_name=class_name,
            student_number=student_number,
            lucky_number=lucky_number,
        )

    async def _ensure_dictionaries(self) -> None:
        """Populate subject, teacher, and category lookup caches if empty."""
        if not self._subjects_cache:
            try:
                subj_data = await self._api_get("Subjects")
                for item in subj_data.get("Subjects", []):
                    if "Id" in item and "Name" in item:
                        self._subjects_cache[int(item["Id"])] = str(item["Name"])
            except LibrusApiError:
                _LOGGER.debug("Unable to load Subjects dictionary")

        if not self._users_cache:
            try:
                users_data = await self._api_get("Users")
                for item in users_data.get("Users", []):
                    if "Id" in item:
                        first = item.get("FirstName", "")
                        last = item.get("LastName", "")
                        full = f"{first} {last}".strip()
                        if full:
                            self._users_cache[int(item["Id"])] = full
            except LibrusApiError:
                _LOGGER.debug("Unable to load Users dictionary")

        if not self._grade_categories_cache:
            try:
                cat_data = await self._api_get("Grades/Categories")
                for item in cat_data.get("Categories", []):
                    if "Id" in item:
                        weight = item.get("Weight")
                        self._grade_categories_cache[int(item["Id"])] = (
                            str(item.get("Name", "")),
                            weight,
                        )
            except LibrusApiError:
                _LOGGER.debug("Unable to load Grades/Categories dictionary")

        if not self._note_categories_cache:
            try:
                ncat_data = await self._api_get("Notes/Categories")
                for item in ncat_data.get("Categories", []):
                    if "Id" in item:
                        positive_flag = item.get("Positive")
                        is_pos = (
                            bool(positive_flag)
                            if positive_flag is not None
                            else None
                        )
                        self._note_categories_cache[int(item["Id"])] = (
                            str(item.get("Name", "")),
                            is_pos,
                        )
            except LibrusApiError:
                _LOGGER.debug("Unable to load Notes/Categories dictionary")

    async def async_get_grades(self) -> list[LibrusGrade]:
        """Fetch and enrich student's grades sorted from newest to oldest.

        Supports both the JSON Gateway (`Grades`) and HTML scraping of `/przegladaj_oceny/uczen`
        (matching `Mati365/librus-api` `info.getGrades()`).
        """
        try:
            await self._ensure_dictionaries()
            grades_data = await self._api_get("Grades")
            if "Grades" in grades_data:
                comments_map: dict[int, str] = {}
                try:
                    comments_data = await self._api_get("Grades/Comments")
                    for c_item in comments_data.get("Comments", []):
                        if "Id" in c_item and "Text" in c_item:
                            comments_map[int(c_item["Id"])] = str(c_item["Text"]).strip()
                except LibrusApiError:
                    pass

                parsed_grades: list[LibrusGrade] = []
                for raw in grades_data.get("Grades", []):
                    grade_id = str(raw.get("Id", ""))
                    if not grade_id:
                        continue

                    subj_id = (raw.get("Subject") or {}).get("Id")
                    subject_name = self._subjects_cache.get(
                        int(subj_id) if subj_id is not None else -1,
                        "Inny przedmiot",
                    )

                    cat_id = (raw.get("Category") or {}).get("Id")
                    cat_name, cat_weight = self._grade_categories_cache.get(
                        int(cat_id) if cat_id is not None else -1,
                        ("", None),
                    )

                    teacher_id = (raw.get("AddedBy") or {}).get("Id")
                    teacher_name = self._users_cache.get(
                        int(teacher_id) if teacher_id is not None else -1,
                        "",
                    )

                    comment_ids = raw.get("Comments") or []
                    comment_texts = [
                        comments_map[int(cid["Id"])]
                        for cid in comment_ids
                        if isinstance(cid, dict)
                        and "Id" in cid
                        and int(cid["Id"]) in comments_map
                    ]

                    parsed_grades.append(
                        LibrusGrade(
                            grade_id=grade_id,
                            subject=subject_name,
                            value=str(raw.get("Grade", "")).strip(),
                            date=str(raw.get("Date", "")),
                            added_at=str(raw.get("AddDate", raw.get("Date", ""))),
                            weight=raw.get("Weight", cat_weight),
                            category=cat_name,
                            teacher=teacher_name,
                            comment="; ".join(comment_texts),
                            semester=raw.get("Semester"),
                            is_final=bool(
                                raw.get("IsFinal") or raw.get("IsFinalProposition")
                            ),
                        )
                    )

                parsed_grades.sort(
                    key=lambda g: (
                        g.added_at or g.date,
                        int(g.grade_id) if g.grade_id.isdigit() else 0,
                    ),
                    reverse=True,
                )
                return parsed_grades[: self._max_items]
        except LibrusApiError:
            _LOGGER.debug("Falling back to HTML /przegladaj_oceny/uczen for grades")

        grades_html = await self._synergia_html_get(LIBRUS_SYNERGIA_GRADES_URL)
        return self.parse_grades_html(grades_html, limit=self._max_items)

    @staticmethod
    def parse_grades_html(
        grades_html: str,
        limit: int = DEFAULT_MAX_ITEMS,
    ) -> list[LibrusGrade]:
        """Parse `/przegladaj_oceny/uczen` HTML (matching `Mati365/librus-api` `info.getGrades()`)."""
        if not grades_html:
            return []

        root = _parse_html_tree(grades_html)
        grades: list[LibrusGrade] = []

        for tr in _find_all_nodes(root, {"tr"}, recursive=True):
            cells = _find_all_nodes(tr, {"td"}, recursive=False)
            if len(cells) < 3:
                continue

            subject = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
            if not subject or subject.lower() in {"przedmiot", "zachowanie"}:
                continue

            # Find all grade links <a class="ocena" title="Kategoria: ...&#10;Data: ...">
            for a_node in _find_all_nodes(tr, {"a"}, recursive=True):
                cls_attr = a_node.attrs.get("class", "").lower()
                if "ocena" not in cls_attr:
                    continue

                grade_val = a_node.get_text(" ", strip=True)
                if not grade_val:
                    continue

                title_attr = a_node.attrs.get("title", "")
                meta: dict[str, str] = {}
                for match in _KV_TITLE_RE.finditer(title_attr):
                    k = match.group(1).strip().lower()
                    v = match.group(2).strip()
                    meta[k] = v

                category = meta.get("kategoria", "")
                date_str = meta.get("data", "")
                teacher = meta.get("nauczyciel", "") or meta.get("dodał", "")
                weight_str = meta.get("waga", "")
                comment = meta.get("komentarz", "")
                weight: int | float | None = (
                    int(weight_str) if weight_str.isdigit() else None
                )

                raw_id_seed = f"{subject}|{grade_val}|{date_str}|{category}|{teacher}|{comment}"
                grade_id = hashlib.sha1(raw_id_seed.encode("utf-8")).hexdigest()[:12]

                grades.append(
                    LibrusGrade(
                        grade_id=grade_id,
                        subject=subject,
                        value=grade_val,
                        date=date_str,
                        added_at=date_str,
                        weight=weight,
                        category=category,
                        teacher=teacher,
                        comment=comment,
                    )
                )

        grades.sort(key=lambda g: g.date, reverse=True)
        return grades[:limit]

    async def async_get_notes(self) -> list[LibrusNote]:
        """Fetch and enrich student's behavior notes (Uwagi / Pochwały).

        Supports both JSON Gateway (`Notes`) and HTML scraping of `/uwagi`
        (matching `Mati365/librus-api` `info.getNotifications()` / notes).
        """
        try:
            await self._ensure_dictionaries()
            notes_data = await self._api_get("Notes")
            if "Notes" in notes_data:
                parsed_notes: list[LibrusNote] = []
                for raw in notes_data.get("Notes", []):
                    note_id = str(raw.get("Id", ""))
                    if not note_id:
                        continue

                    cat_id = (raw.get("Category") or {}).get("Id")
                    cat_name, is_positive = self._note_categories_cache.get(
                        int(cat_id) if cat_id is not None else -1,
                        ("Uwaga", None),
                    )
                    if raw.get("Positive") is not None:
                        is_positive = bool(raw.get("Positive"))

                    teacher_id = (raw.get("Teacher") or raw.get("AddedBy") or {}).get("Id")
                    teacher_name = self._users_cache.get(
                        int(teacher_id) if teacher_id is not None else -1,
                        "",
                    )

                    raw_text = str(raw.get("Text", "")).strip()
                    clean_content = html_to_plain_text(raw_text)

                    parsed_notes.append(
                        LibrusNote(
                            note_id=note_id,
                            teacher=teacher_name,
                            category=cat_name,
                            content=clean_content,
                            date=str(raw.get("Date", raw.get("AddDate", ""))),
                            positive=is_positive,
                        )
                    )

                parsed_notes.sort(
                    key=lambda n: (n.date, int(n.note_id) if n.note_id.isdigit() else 0),
                    reverse=True,
                )
                return parsed_notes[: self._max_items]
        except LibrusApiError:
            _LOGGER.debug("Falling back to HTML /uwagi for notes")

        try:
            notes_html = await self._synergia_html_get(LIBRUS_SYNERGIA_NOTES_URL)
            return self.parse_notes_html(notes_html, limit=self._max_items)
        except LibrusApiError:
            return []

    @staticmethod
    def parse_notes_html(
        notes_html: str,
        limit: int = DEFAULT_MAX_ITEMS,
    ) -> list[LibrusNote]:
        """Parse `/uwagi` HTML table into `LibrusNote` objects."""
        if not notes_html:
            return []

        root = _parse_html_tree(notes_html)
        notes: list[LibrusNote] = []

        for table in _find_all_nodes(root, {"table"}, recursive=True):
            rows = _find_all_nodes(table, {"tr"}, recursive=True)
            note_content = ""
            note_date = ""
            note_teacher = ""
            note_category = "Uwaga"

            for tr in rows:
                cells = _find_all_nodes(tr, {"th", "td"}, recursive=False)
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(" ", strip=True).lower()
                val = cells[1].get_text(" ", strip=True)
                if "treść" in label:
                    note_content = val
                elif "data" in label:
                    note_date = val
                elif "nauczyciel" in label or "dodał" in label:
                    note_teacher = val
                elif "kategoria" in label or "rodzaj" in label:
                    note_category = val

            if note_content:
                seed = f"{note_date}|{note_teacher}|{note_content}"
                note_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
                is_pos: bool | None = None
                if "pozytywn" in note_category.lower() or "pochwał" in note_category.lower():
                    is_pos = True
                elif "negatywn" in note_category.lower() or "uwag" in note_category.lower():
                    is_pos = False

                notes.append(
                    LibrusNote(
                        note_id=note_id,
                        teacher=note_teacher,
                        category=note_category,
                        content=note_content,
                        date=note_date,
                        positive=is_pos,
                    )
                )

        notes.sort(key=lambda n: n.date, reverse=True)
        return notes[:limit]

    async def async_get_messages(self) -> list[LibrusMessage]:
        """Fetch incoming messages from Librus and format them into readable Markdown & text."""
        if not self._authenticated:
            await self.async_authenticate()

        # First attempt JSON Messages endpoint if available, then use HTML Wiadomości (`inbox.listInbox`)
        messages = await self._try_fetch_json_messages()
        if messages is None:
            messages = await self._fetch_html_messages()

        return messages[: self._max_items]

    async def _try_fetch_json_messages(self) -> list[LibrusMessage] | None:
        """Attempt to fetch messages from JSON endpoint if supported by account scope."""
        try:
            data = await self._api_get("Messages")
        except LibrusApiError:
            return None

        raw_list = data.get("Messages")
        if not isinstance(raw_list, list):
            return None

        results: list[LibrusMessage] = []
        for item in raw_list[: self._max_items]:
            msg_id = str(item.get("Id") or item.get("MessageId") or "")
            if not msg_id:
                continue

            sender_raw = str(
                item.get("SenderName")
                or (item.get("Sender") or {}).get("Name")
                or item.get("Sender")
                or "Nieznany nadawca"
            )
            sender = format_sender_name(sender_raw)
            subject = str(item.get("Subject") or item.get("Topic") or "(Brak tematu)").strip()
            sent_at = str(item.get("SendDate") or item.get("Date") or "")
            is_unread = not bool(item.get("Read", not item.get("Unread", False)))
            body_html = str(item.get("Body") or item.get("Content") or "")
            attachments = [
                str(att.get("Filename") or att.get("Name") or "Załącznik")
                for att in (item.get("Attachments") or [])
                if isinstance(att, dict)
            ]
            has_attachments = bool(attachments or item.get("HasAttachments"))

            body_markdown = format_message_markdown(
                sender=sender,
                subject=subject,
                sent_at=sent_at,
                body_html=body_html,
                attachments=attachments,
            )
            body_text = html_to_plain_text(body_html)

            results.append(
                LibrusMessage(
                    message_id=msg_id,
                    sender=sender,
                    subject=subject,
                    sent_at=sent_at,
                    is_unread=is_unread,
                    body_html=body_html,
                    body_markdown=body_markdown,
                    body_text=body_text,
                    has_attachments=has_attachments,
                    attachments=attachments,
                )
            )

        return results

    async def _fetch_html_messages(self) -> list[LibrusMessage]:
        """Scrape and sanitize incoming messages from `/wiadomosci` (matching `Mati365/librus-api` `inbox`)."""
        try:
            inbox_html = await self._synergia_html_get(LIBRUS_SYNERGIA_MESSAGES_URL)
        except LibrusApiError:
            return []

        inbox_entries = self.parse_inbox_html(inbox_html, limit=self._max_items)
        messages: list[LibrusMessage] = []

        for entry in inbox_entries:
            detail_html = ""
            if entry["url"]:
                try:
                    detail_html = await self._synergia_html_get(entry["url"], retry_auth=False)
                except LibrusApiError:
                    _LOGGER.debug("Failed to load message detail %s", entry["message_id"])

            body_html, attachments = self.parse_message_detail_html(detail_html)
            has_attachments = bool(entry["has_attachments"] or attachments)

            body_markdown = format_message_markdown(
                sender=entry["sender"],
                subject=entry["subject"],
                sent_at=entry["sent_at"],
                body_html=body_html,
                attachments=attachments,
            )
            body_text = html_to_plain_text(body_html)

            messages.append(
                LibrusMessage(
                    message_id=entry["message_id"],
                    sender=entry["sender"],
                    subject=entry["subject"],
                    sent_at=entry["sent_at"],
                    is_unread=entry["is_unread"],
                    body_html=body_html,
                    body_markdown=body_markdown,
                    body_text=body_text,
                    has_attachments=has_attachments,
                    attachments=attachments,
                    url=entry["url"],
                )
            )

        return messages

    @staticmethod
    def parse_inbox_html(inbox_html: str, limit: int = DEFAULT_MAX_ITEMS) -> list[dict[str, Any]]:
        """Parse the Librus Synergia Wiadomości inbox HTML table into structured metadata rows."""
        if not inbox_html:
            return []

        root = _parse_html_tree(inbox_html)
        tables = _find_all_nodes(root, {"table"}, recursive=True)
        if not tables:
            return []

        target_table = tables[0]
        for tbl in tables:
            cls_attr = tbl.attrs.get("class", "").lower()
            if "decorated" in cls_attr or "wiadomosci" in cls_attr:
                target_table = tbl
                break

        rows = _find_all_nodes(target_table, {"tr"}, recursive=True)
        entries: list[dict[str, Any]] = []

        for row in rows:
            cells = _find_all_nodes(row, {"td"}, recursive=False)
            if len(cells) < 4:
                continue

            links = _find_all_nodes(row, {"a"}, recursive=True)
            link_node: _DOMNode | None = None
            for lnk in links:
                href_val = lnk.attrs.get("href", "")
                if _MESSAGE_ID_RE.search(href_val):
                    link_node = lnk
                    break
            if link_node is None and links:
                link_node = links[0]
            if link_node is None:
                continue

            href = link_node.attrs.get("href", "")
            id_match = _MESSAGE_ID_RE.search(href)
            msg_id = id_match.group(1) if id_match else href.rstrip("/").split("/")[-1]
            if not msg_id:
                continue

            row_style = row.attrs.get("style", "").lower()
            is_unread = (
                "bold" in row_style
                or any("bold" in td.attrs.get("style", "").lower() for td in cells)
                or bool(_find_all_nodes(row, {"b", "strong"}, recursive=True))
            )

            has_attachments = (
                bool(_find_all_nodes(cells[1], {"img"}, recursive=True))
                if len(cells) >= 5
                else False
            )
            sender_idx = 2 if len(cells) >= 5 else 1
            subject_idx = 3 if len(cells) >= 5 else 2
            date_idx = 4 if len(cells) >= 5 else 3

            raw_sender = cells[sender_idx].get_text(" ", strip=True)
            raw_subject = cells[subject_idx].get_text(" ", strip=True)
            raw_date = cells[date_idx].get_text(" ", strip=True)

            entries.append(
                {
                    "message_id": msg_id,
                    "sender": format_sender_name(raw_sender),
                    "subject": raw_subject or "(Brak tematu)",
                    "sent_at": raw_date,
                    "is_unread": is_unread,
                    "has_attachments": has_attachments,
                    "url": href,
                }
            )
            if len(entries) >= limit:
                break

        return entries

    @staticmethod
    def parse_message_detail_html(detail_html: str) -> tuple[str, list[str]]:
        """Extract the raw message body HTML and attachment filenames from a message detail page."""
        if not detail_html:
            return "", []

        body_html = detail_html
        container_match = re.search(
            r'<div[^>]+(?:class="[^"]*container-message-content[^"]*"|id="message-content")[^>]*>(.*?)</div>',
            detail_html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if container_match:
            body_html = container_match.group(1)

        root = _parse_html_tree(detail_html)
        attachments: list[str] = []
        for node in _find_all_nodes(root, {"a", "span", "div"}, recursive=True):
            cls_val = node.attrs.get("class", "")
            href_val = node.attrs.get("href", "")
            if "attachment-name" in cls_val or "pobierz_zalacznik" in href_val:
                name = node.get_text(" ", strip=True)
                if name and name not in attachments:
                    attachments.append(name)

        return body_html, attachments

    async def async_fetch_snapshot(self) -> LibrusDataSnapshot:
        """Fetch a complete data snapshot for the student account."""
        async with self._lock:
            student = await self.async_get_student_profile()
            messages, grades, notes = await asyncio.gather(
                self.async_get_messages(),
                self.async_get_grades(),
                self.async_get_notes(),
            )
            return LibrusDataSnapshot(
                student=student,
                messages=messages,
                grades=grades,
                notes=notes,
                fetched_at=datetime.now(),
            )
