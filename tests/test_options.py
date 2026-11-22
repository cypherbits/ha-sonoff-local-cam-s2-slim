"""Tests for the options flow reloading the coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .fakes import PASSWORD, FakeSonoffCamera


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False, CONF_SCAN_INTERVAL: 60},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sonoff_cam_local.coordinator.SonoffCamera",
        FakeSonoffCamera,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_options_change_reloads_coordinator(hass: HomeAssistant) -> None:
    """Changing the poll interval takes effect without a restart."""
    entry = await _setup(hass)
    assert entry.runtime_data.update_interval == timedelta(seconds=60)

    with (
        patch(
            "custom_components.sonoff_cam_local.coordinator.SonoffCamera",
            FakeSonoffCamera,
        ),
        patch(
            "custom_components.sonoff_cam_local.config_flow.SonoffCamera",
            FakeSonoffCamera,
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL: 120, CONF_ENABLE_ONVIF: False},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    assert entry.options[CONF_SCAN_INTERVAL] == 120
    assert entry.runtime_data.update_interval == timedelta(seconds=120)
