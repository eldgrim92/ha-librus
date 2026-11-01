#!/usr/bin/env python3
"""Local standalone CLI tool to test and debug Librus Synergia login and data fetching.

Works with zero third-party dependencies (uses Python standard library `urllib` + `http.cookiejar`),
and also tests `custom_components/librus` parsers so you can run it directly on your Mac.

Usage:
    python3 scripts/debug_librus_login.py
    python3 scripts/debug_librus_login.py --username 1234567u
    python3 scripts/debug_librus_login.py --username 1234567u --password "secret"
"""

from __future__ import annotations

import argparse
import getpass
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

# Ensure project root is on sys.path so we can import the integration's HTML/Markdown parsers
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _mask_secret(val: str) -> str:
    if len(val) <= 2:
        return "***"
    return val[0] + "*" * (len(val) - 2) + val[-1]


class LibrusLoginDebugger:
    """Step-by-step HTTP tracer for Librus Synergia OAuth & Portal Rodzina login."""

    def __init__(self, username: str, password: str, verbose: bool = True) -> None:
        self.username = username.strip()
        self.password = password
        self.verbose = verbose
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
        )

    def _print_cookies(self) -> None:
        cookies = [f"{c.domain}: {c.name}={c.value[:12]}..." for c in self.cookie_jar]
        print(f"    🍪 Active Cookies ({len(cookies)}): {', '.join(cookies) if cookies else 'None'}")

    def request(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        step_label: str = "",
    ) -> tuple[int, str, str, dict[str, Any] | None]:
        """Execute an HTTP request and print full diagnostic trace."""
        print(f"\n{'=' * 72}")
        print(f"➡️  [{step_label}] {method} {url}")
        if data:
            safe_data = {
                k: (_mask_secret(v) if k in {"pass", "password"} else v)
                for k, v in data.items()
            }
            print(f"    Payload: {safe_data}")

        req_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, text/html, */*; q=0.01",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if headers:
            req_headers.update(headers)

        encoded_data = (
            urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        )
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers=req_headers,
            method=method,
        )

        try:
            with self.opener.open(req, timeout=25) as resp:
                status = resp.status
                final_url = resp.geturl()
                resp_headers = dict(resp.info())
                raw_bytes = resp.read()
                body = raw_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            status = err.code
            final_url = err.geturl()
            resp_headers = dict(err.headers) if err.headers else {}
            raw_bytes = err.read() if err.fp else b""
            body = raw_bytes.decode("utf-8", errors="replace")
            print(f"❗ HTTP Error {status} ({err.reason}) at {final_url}")
            print(f"    Error Response Headers: {resp_headers}")
            print(f"    Error Response Body:\n{body}\n")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Network Error: {exc}")
            raise

        print(f"⬅️  Status: HTTP {status}")
        if final_url != url:
            print(f"    Redirected to: {final_url}")
        self._print_cookies()

        parsed_json: dict[str, Any] | None = None
        try:
            parsed_json = json.loads(body)
            print(f"    JSON Response: {json.dumps(parsed_json, ensure_ascii=False)}")
        except Exception:  # noqa: BLE001
            if status >= 400:
                print(f"    Full Error Body ({len(body)} chars):\n{body}")
            else:
                snippet = " ".join(body.strip().split())[:220]
                print(f"    HTML/Text Snippet ({len(body)} chars): {snippet}...")

        return status, final_url, body, parsed_json

    def run_login_flow(self) -> bool:
        """Run the modern `Mati365/librus-api` login flow (`portalRodzina` -> `OAuth` -> `Grant`)."""
        ts = int(time.time())
        portal_init_url = f"https://synergia.librus.pl/loguj/portalRodzina?v={ts}"

        # Step 1A: Bootstrap session on synergia.librus.pl/loguj/portalRodzina?v=<timestamp>
        status, final_url, _, _ = self.request(
            "GET",
            portal_init_url,
            step_label="STEP 1A: Bootstrap Synergia Session (/loguj/portalRodzina)",
        )

        # Step 1B: Ensure OAuth Authorization form session is initialized if not already redirected there
        oauth_auth_url = (
            "https://api.librus.pl/OAuth/Authorization"
            "?client_id=46&response_type=code&scope=mydata"
        )
        if "api.librus.pl/OAuth/Authorization" not in final_url:
            self.request(
                "GET",
                oauth_auth_url,
                step_label="STEP 1B: Initialize OAuth Authorization Cookie",
            )

        # Step 2: POST credentials to https://api.librus.pl/OAuth/Authorization?client_id=46
        oauth_login_url = "https://api.librus.pl/OAuth/Authorization?client_id=46"
        status, _, _, login_json = self.request(
            "POST",
            oauth_login_url,
            data={
                "action": "login",
                "login": self.username,
                "pass": self.password,
            },
            headers={
                "Referer": oauth_auth_url,
                "Origin": "https://api.librus.pl",
                "X-Requested-With": "XMLHttpRequest",
            },
            step_label="STEP 2: POST Credentials to OAuth/Authorization",
        )

        if status in (401, 403):
            print("\n❌ Login rejected with HTTP 401/403.")
            return False

        if isinstance(login_json, dict):
            if login_json.get("status") == "error" or login_json.get("errors"):
                print(f"\n❌ Librus returned login error: {login_json}")
                return False

        go_to = (login_json or {}).get("goTo") if isinstance(login_json, dict) else None
        grant_url = (
            f"https://api.librus.pl{go_to}"
            if go_to and str(go_to).startswith("/")
            else (str(go_to) if go_to else "https://api.librus.pl/OAuth/Authorization/Grant?client_id=46")
        )

        # Step 3: Follow goTo / Grant URL to complete OAuth handshake and land on synergia.librus.pl
        status, final_url, body, grant_json = self.request(
            "GET",
            grant_url,
            step_label="STEP 3: Follow OAuth Grant / 2FA Redirect",
        )

        # If Step 3 returned another JSON redirect (e.g., from /2FA to /Grant), follow it
        if isinstance(grant_json, dict) and grant_json.get("goTo"):
            next_goto = str(grant_json["goTo"])
            next_url = (
                f"https://api.librus.pl{next_goto}"
                if next_goto.startswith("/")
                else next_goto
            )
            status, final_url, body, _ = self.request(
                "GET",
                next_url,
                step_label="STEP 3B: Follow Secondary goTo Redirect",
            )

        # Step 4: Test fetching `/informacje` and `gateway/api/2.0/Me`
        print(f"\n{'=' * 72}")
        print("🔍 VERIFYING DATA ACCESS AFTER LOGIN")

        me_status, _, _, me_json = self.request(
            "GET",
            "https://synergia.librus.pl/gateway/api/2.0/Me",
            step_label="VERIFY A: JSON Gateway (/gateway/api/2.0/Me)",
        )

        info_status, info_url, info_html, _ = self.request(
            "GET",
            "https://synergia.librus.pl/informacje",
            step_label="VERIFY B: Synergia Web (/informacje)",
        )

        msg_status, _, msg_html, _ = self.request(
            "GET",
            "https://synergia.librus.pl/wiadomosci",
            step_label="VERIFY C: Synergia Messages (/wiadomosci)",
        )

        # Parse using the integration's parsers if available
        try:
            from custom_components.librus.api.client import LibrusApiClient

            profile = LibrusApiClient.parse_account_info_html(
                info_html, default_username=self.username
            )
            inbox = LibrusApiClient.parse_inbox_html(msg_html, limit=5)
            print(f"\n{'=' * 72}")
            print("✅ PARSED SUMMARY:")
            print(f"   • Student Name (from /informacje): {profile.student_name!r}")
            print(f"   • Class (from /informacje):        {profile.class_name!r}")
            print(f"   • Lucky Number:                    {profile.lucky_number!r}")
            if isinstance(me_json, dict) and "Me" in me_json:
                acc = me_json["Me"].get("Account", {})
                print(
                    f"   • Student Name (from /api/2.0/Me): "
                    f"{acc.get('FirstName', '')} {acc.get('LastName', '')}"
                )
            print(f"   • Recent Inbox Messages Parsed:    {len(inbox)}")
            for idx, m in enumerate(inbox[:3], 1):
                print(
                    f"     {idx}. [{m['sent_at']}] {m['sender']} — {m['subject']} "
                    f"(unread={m['is_unread']})"
                )
        except Exception as parse_err:  # noqa: BLE001
            print(f"⚠️  Parser check warning: {parse_err}")

        is_logged_in = (
            (me_status == 200 and isinstance(me_json, dict) and "Me" in me_json)
            or (
                info_status == 200
                and "loguj" not in info_url.lower()
                and ("Imię i nazwisko" in info_html or "uczen" in info_url.lower())
            )
        )
        return is_logged_in


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test and debug Librus Synergia login step-by-step."
    )
    parser.add_argument(
        "-u",
        "--username",
        help="Librus Synergia username (e.g. 1234567u)",
    )
    parser.add_argument(
        "-p",
        "--password",
        help="Librus Synergia password (will prompt securely if omitted)",
    )
    args = parser.parse_args()

    username = args.username or input("Librus Username (e.g. 1234567u): ").strip()
    password = args.password or getpass.getpass("Librus Password: ")

    if not username or not password:
        print("Error:Both username and password are required.")
        return 1

    debugger = LibrusLoginDebugger(username=username, password=password)
    success = debugger.run_login_flow()
    print(f"\n{'=' * 72}")
    if success:
        print("🎉 LOGIN & DATA FETCH SUCCEEDED!")
        return 0

    print("❌ LOGIN FAILED — copy the output above (passwords are masked) and share it.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

