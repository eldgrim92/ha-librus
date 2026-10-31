"""Unit tests for the Librus Message Readability Engine and HTML scrapers."""

from __future__ import annotations

import unittest

from tests.conftest import install_ha_stubs

install_ha_stubs()

from custom_components.librus.api.client import LibrusApiClient  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
