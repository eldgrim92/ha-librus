"""Unit tests for the Librus Message Readability Engine and HTML scrapers."""

from __future__ import annotations

import unittest

from tests.conftest import install_ha_stubs

install_ha_stubs()

from custom_components.librus.api.client import LibrusApiClient, LibrusAuthError  # noqa: E402
from custom_components.librus.const import (  # noqa: E402
    LIBRUS_OAUTH_AUTH_URL,
    LIBRUS_OAUTH_GRANT_URL,
    LIBRUS_OAUTH_LOGIN_URL,
)
from custom_components.librus.api.parser import (  # noqa: E402
    format_message_markdown,
    format_sender_name,
    html_to_clean_markdown,
    html_to_plain_text,
)


class TestMessageParser(unittest.TestCase):
    """Test suite for HTML message sanitization and readable Markdown formatting."""

    def test_format_sender_name_removes_duplicates_and_normalizes_role(self) -> None:
        self.assertEqual(
            format_sender_name("Nowak Anna (Nowak Anna) [Wychowawca]"),
            "Nowak Anna (Wychowawca)",
        )
        self.assertEqual(
            format_sender_name("  Kowalski\xa0Piotr  "),
            "Kowalski Piotr",
        )
        self.assertEqual(format_sender_name(""), "Nieznany nadawca")

    def test_html_to_clean_markdown_strips_styles_and_preserves_structure(self) -> None:
        messy_html = """
        <html>
        <head><style>.red { color: red; }</style></head>
        <body>
            <p style="font-family: Arial;">Dzień&nbsp;dobry,</p>
            <p>Przypominam o <b>wycieczce szkolnej</b> w dniu <i>15 listopada</i>.</p>
            <ul>
                <li>Zbiórka o 7:45</li>
                <li>Powrót około 16:30</li>
            </ul>
            <p>Szczegóły: <a href="https://szkola.przyklad.pl/wycieczka">Plan wycieczki</a>
            lub bezpośrednio pod adresem https://librus.pl/info</p>
        </body>
        </html>
        """
        md = html_to_clean_markdown(messy_html)
        self.assertNotIn("<style>", md)
        self.assertNotIn("font-family", md)
        self.assertIn("Dzień dobry,", md)
        self.assertIn("**wycieczce szkolnej**", md)
        self.assertIn("*15 listopada*", md)
        self.assertIn("- Zbiórka o 7:45", md)
        self.assertIn("- Powrót około 16:30", md)
        self.assertIn("[Plan wycieczki](https://szkola.przyklad.pl/wycieczka)", md)
        self.assertIn("[https://librus.pl/info](https://librus.pl/info)", md)

    def test_html_to_plain_text_truncation_and_newlines(self) -> None:
        raw_html = "<p>Pierwsza linia<br>Druga linia</p><p>Trzeci akapit</p>"
        text = html_to_plain_text(raw_html)
        self.assertEqual(text, "Pierwsza linia\nDruga linia\n\nTrzeci akapit")

        truncated = html_to_plain_text(raw_html, max_length=15)
        self.assertEqual(len(truncated), 15)
        self.assertTrue(truncated.endswith("…"))

    def test_format_message_markdown_with_attachments(self) -> None:
        md = format_message_markdown(
            sender="Nowak Anna (Nowak Anna) [Nauczyciel]",
            subject="Zgoda na konkurs",
            sent_at="2026-10-31 14:20",
            body_html="<p>Proszę o podpisanie <strong>zgody</strong>.</p>",
            attachments=["zgoda_konkurs.pdf", "regulamin.pdf"],
        )
        self.assertIn("### 📩 Zgoda na konkurs", md)
        self.assertIn("**Od:** Nowak Anna (Nauczyciel)", md)
        self.assertIn("**Data:** 2026-10-31 14:20", md)
        self.assertIn("**Załączniki (2):** 📎 zgoda_konkurs.pdf, regulamin.pdf", md)
        self.assertIn("Proszę o podpisanie **zgody** .", md.replace("**zgody**.", "**zgody** ."))

    def test_parse_inbox_and_detail_html(self) -> None:
        inbox_html = """
        <table class="decorated wiadomosci">
            <tbody>
                <tr style="font-weight: bold;">
                    <td><input type="checkbox"/></td>
                    <td><img src="/img/attachment.png" /></td>
                    <td>Wiśniewski Marek (Wiśniewski Marek) [Dyrektor]</td>
                    <td><a href="/wiadomosci/1/5/998877/f0">Zebranie z rodzicami</a></td>
                    <td>2026-10-31 18:00</td>
                </tr>
                <tr>
                    <td><input type="checkbox"/></td>
                    <td></td>
                    <td>Kowalczyk Ewa</td>
                    <td><a href="/wiadomosci/1/5/998811/f0">Informacja o ocenach</a></td>
                    <td>2026-10-29 10:15</td>
                </tr>
            </tbody>
        </table>
        """
        entries = LibrusApiClient.parse_inbox_html(inbox_html)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["message_id"], "998877")
        self.assertEqual(entries[0]["sender"], "Wiśniewski Marek (Dyrektor)")
        self.assertEqual(entries[0]["subject"], "Zebranie z rodzicami")
        self.assertTrue(entries[0]["is_unread"])
        self.assertTrue(entries[0]["has_attachments"])

        self.assertEqual(entries[1]["message_id"], "998811")
        self.assertFalse(entries[1]["is_unread"])
        self.assertFalse(entries[1]["has_attachments"])

        detail_html = """
        <div class="container-message-content">
            <p>Zapraszam na zebranie w sali <b>204</b>.</p>
        </div>
        <a href="/wiadomosci/pobierz_zalacznik/998877/1">harmonogram.pdf</a>
        """
        body_html, attachments = LibrusApiClient.parse_message_detail_html(detail_html)
        self.assertIn("Zapraszam na zebranie", body_html)
        self.assertEqual(attachments, ["harmonogram.pdf"])

    def test_parse_account_info_grades_and_notes_html_fallbacks(self) -> None:
        info_html = """
        <span class="luckyNumber"><b>17</b></span>
        <table>
            <tr><th>Imię i nazwisko ucznia</th><td>Jan Kowalski</td></tr>
            <tr><th>Klasa</th><td>5b</td></tr>
            <tr><th>Nr w dzienniku</th><td>17</td></tr>
        </table>
        """
        profile = LibrusApiClient.parse_account_info_html(info_html, default_username="123u")
        self.assertEqual(profile.student_name, "Jan Kowalski")
        self.assertEqual(profile.class_name, "5b")
        self.assertEqual(profile.student_number, 17)
        self.assertEqual(profile.lucky_number, 17)
        self.assertTrue(profile.is_lucky_today)

        grades_html = """
        <table>
            <tr>
                <td>1</td>
                <td>Matematyka</td>
                <td>
                    <a class="ocena" title="Kategoria: Sprawdzian\nData: 2026-10-30\nNauczyciel: Piotr Wiśniewski\nWaga: 3\nKomentarz: Ułamki">5-</a>
                </td>
            </tr>
        </table>
        """
        grades = LibrusApiClient.parse_grades_html(grades_html)
        self.assertEqual(len(grades), 1)
        self.assertEqual(grades[0].subject, "Matematyka")
        self.assertEqual(grades[0].value, "5-")
        self.assertEqual(grades[0].weight, 3)
        self.assertEqual(grades[0].category, "Sprawdzian")
        self.assertEqual(grades[0].teacher, "Piotr Wiśniewski")
        self.assertEqual(grades[0].comment, "Ułamki")

        notes_html = """
        <table>
            <tr><th>Data</th><td>2026-10-28</td></tr>
            <tr><th>Nauczyciel</th><td>Anna Nowak</td></tr>
            <tr><th>Kategoria</th><td>Pochwała</td></tr>
            <tr><th>Treść</th><td>Wzorowa pomoc przy akademii.</td></tr>
        </table>
        """
        notes = LibrusApiClient.parse_notes_html(notes_html)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].teacher, "Anna Nowak")
        self.assertTrue(notes[0].positive)
        self.assertEqual(notes[0].content, "Wzorowa pomoc przy akademii.")


class _FakeResponse:
    def __init__(self, status: int = 200, json_data: dict | None = None, text_data: str = "", url: str = "") -> None:
        self.status = status
        self._json = json_data
        self._text = text_data
        self.url = url

    async def json(self, content_type: str | None = None) -> dict | None:
        return self._json

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class _FakeSession:
    def __init__(self, post_json: dict | None = None) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self._post_json = post_json if post_json is not None else {"status": "ok", "goTo": "/OAuth/Authorization/Grant?client_id=46"}

    def get(self, url: str, **kwargs) -> _FakeResponse:
        self.calls.append(("GET", url, None))
        return _FakeResponse(status=200, json_data={})

    def post(self, url: str, data: dict | None = None, **kwargs) -> _FakeResponse:
        self.calls.append(("POST", url, data))
        return _FakeResponse(status=200, json_data=self._post_json)


class TestMati365AuthorizeFlow(unittest.IsolatedAsyncioTestCase):
    """Verify `async_authenticate` executes the `Mati365/librus-api` OAuth Grant sequence."""

    async def test_authorize_calls_oauth_login_and_grant(self) -> None:
        session = _FakeSession()
        client = LibrusApiClient(username="123456u", password="secret", session=session)
        await client.async_authenticate()

        self.assertEqual(session.calls[0][0], "GET")
        self.assertEqual(session.calls[0][1], LIBRUS_OAUTH_AUTH_URL)

        self.assertEqual(session.calls[1][0], "POST")
        self.assertEqual(session.calls[1][1], LIBRUS_OAUTH_LOGIN_URL)
        self.assertEqual(
            session.calls[1][2],
            {"action": "login", "login": "123456u", "pass": "secret"},
        )

        self.assertEqual(session.calls[2][0], "GET")
        self.assertEqual(session.calls[2][1], LIBRUS_OAUTH_GRANT_URL)

    async def test_authorize_raises_on_error_status(self) -> None:
        session = _FakeSession(post_json={"status": "error", "errors": [{"message": "Nieprawidłowy login"}]})
        client = LibrusApiClient(username="123456u", password="wrong", session=session)
        with self.assertRaises(LibrusAuthError):
            await client.async_authenticate()


if __name__ == "__main__":
    unittest.main()
