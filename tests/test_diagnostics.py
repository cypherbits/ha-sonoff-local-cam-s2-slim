"""Diagnostics tests: the dump must be redacted."""

from __future__ import annotations

import json
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DOMAIN,
)
from custom_components.sonoff_cam_local.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .fakes import PASSWORD, RTSP_PASSWORD, FakeSonoffCamera


async def test_diagnostics_are_redacted(hass: HomeAssistant) -> None:
    """Passwords, SSIDs and inline URL credentials never leak."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", FakeSonoffCamera):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    blob = json.dumps(diagnostics)

    assert diagnostics["config_entry"]["has_admin_password"] is True
    assert diagnostics["onvif"]["password"] == "***REDACTED***"
    assert RTSP_PASSWORD not in blob
    assert PASSWORD not in blob
    assert "home" not in json.dumps(diagnostics["wifi_config"])
