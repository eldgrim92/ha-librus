"""Unit tests for multi-child ConfigFlow and OptionsFlow (configurable sync interval)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from tests.conftest import install_ha_stubs

install_ha_stubs()

from homeassistant.config_entries import AbortFlow, ConfigEntry  # noqa: E402
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME  # noqa: E402

from custom_components.librus.api import (  # noqa: E402
    LibrusAuthError,
    LibrusConnectionError,
    StudentProfile,
)
from custom_components.librus.config_flow import (  # noqa: E402
    LibrusConfigFlow,
    LibrusOptionsFlowHandler,
)
from custom_components.librus.const import (  # noqa: E402
    CONF_MAX_ITEMS,
    CONF_STUDENT_NAME,
    CONF_SYNC_INTERVAL,
)


class TestLibrusConfigFlow(unittest.IsolatedAsyncioTestCase):
    """Tests for adding multiple children and configuring sync period."""

    async def test_setup_multiple_kids_creates_distinct_entries(self) -> None:
        flow_kid1 = LibrusConfigFlow()
        flow_kid2 = LibrusConfigFlow()

        profile_kid1 = StudentProfile(account_id="101", student_name="Jan Kowalski")
        profile_kid2 = StudentProfile(account_id="102", student_name="Zofia Kowalska")

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(return_value=profile_kid1),
        ):
            res1 = await flow_kid1.async_step_user(
                {
                    CONF_USERNAME: "101u",
                    CONF_PASSWORD: "secret1",
                    CONF_STUDENT_NAME: "",
                    CONF_SYNC_INTERVAL: 15,
                    CONF_MAX_ITEMS: 10,
                }
            )

        self.assertEqual(res1["type"], "create_entry")
        self.assertEqual(res1["title"], "Librus - Jan Kowalski")
        self.assertEqual(res1["data"][CONF_STUDENT_NAME], "Jan Kowalski")
        self.assertEqual(res1["options"][CONF_SYNC_INTERVAL], 15)

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(return_value=profile_kid2),
        ):
            res2 = await flow_kid2.async_step_user(
                {
                    CONF_USERNAME: "102u",
                    CONF_PASSWORD: "secret2",
                    CONF_STUDENT_NAME: "Zosia",
                    CONF_SYNC_INTERVAL: 45,
                    CONF_MAX_ITEMS: 20,
                }
            )

        self.assertEqual(res2["type"], "create_entry")
        self.assertEqual(res2["title"], "Librus - Zosia")
        self.assertEqual(res2["data"][CONF_STUDENT_NAME], "Zosia")
        self.assertEqual(res2["options"][CONF_SYNC_INTERVAL], 45)
        self.assertNotEqual(res1["unique_id"], res2["unique_id"])

    async def test_duplicate_kid_account_aborts(self) -> None:
        flow = LibrusConfigFlow()
        flow._existing_unique_ids.add("librus_101_101u")
        profile = StudentProfile(account_id="101", student_name="Jan Kowalski")

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(return_value=profile),
        ):
            with self.assertRaises(AbortFlow):
                await flow.async_step_user(
                    {
                        CONF_USERNAME: "101u",
                        CONF_PASSWORD: "secret1",
                    }
                )

    async def test_invalid_auth_and_connection_errors(self) -> None:
        flow = LibrusConfigFlow()

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(side_effect=LibrusAuthError("Bad credentials")),
        ):
            res = await flow.async_step_user(
                {CONF_USERNAME: "101u", CONF_PASSWORD: "wrong"}
            )
            self.assertEqual(res["type"], "form")
            self.assertEqual(res["errors"]["base"], "invalid_auth")

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(side_effect=LibrusConnectionError("Timeout")),
        ):
            res = await flow.async_step_user(
                {CONF_USERNAME: "101u", CONF_PASSWORD: "wrong"}
            )
            self.assertEqual(res["type"], "form")
            self.assertEqual(res["errors"]["base"], "cannot_connect")

    async def test_options_flow_updates_sync_interval_and_password(self) -> None:
        entry = ConfigEntry(
            entry_id="kid1",
            title="Librus - Jan",
            data={CONF_USERNAME: "101u", CONF_PASSWORD: "old_password"},
            options={CONF_SYNC_INTERVAL: 30, CONF_MAX_ITEMS: 10},
        )
        options_flow = LibrusConfigFlow.async_get_options_flow(entry)
        options_flow.config_entry = entry
        profile = StudentProfile(account_id="101", student_name="Jan")

        with patch(
            "custom_components.librus.config_flow.async_validate_credentials",
            new=AsyncMock(return_value=profile),
        ):
            res = await options_flow.async_step_init(
                {
                    CONF_SYNC_INTERVAL: 10,
                    CONF_MAX_ITEMS: 25,
                    CONF_PASSWORD: "new_password_123",
                }
            )

        self.assertEqual(res["type"], "create_entry")
        self.assertEqual(res["data"][CONF_SYNC_INTERVAL], 10)
        self.assertEqual(res["data"][CONF_MAX_ITEMS], 25)
        self.assertEqual(entry.data[CONF_PASSWORD], "new_password_123")


if __name__ == "__main__":
    unittest.main()

