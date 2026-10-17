"""Tests for the integration services."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DOMAIN,
)

from .fakes import DEVICE_ID, PASSWORD, FakeSonoffCamera


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", FakeSonoffCamera):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_set_wifi_service(hass: HomeAssistant) -> None:
    """The set_wifi service targets the camera device."""
    await _setup(hass)
    assert hass.services.has_service(DOMAIN, "set_wifi")

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEVICE_ID)})
    assert device is not None

    with patch.object(
        FakeSonoffCamera, "set_wifi_config", return_value={}, autospec=True
    ) as mock_set:
        await hass.services.async_call(
            DOMAIN,
            "set_wifi",
            {"device_id": device.id, "ssid": "NewNet", "password": "pw"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_set.await_args.args[1:] == ("NewNet", "pw")


async def test_trigger_alarm_service(hass: HomeAssistant) -> None:
    """The trigger_alarm service sounds the siren with the given duration."""
    await _setup(hass)
    assert hass.services.has_service(DOMAIN, "trigger_alarm")

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEVICE_ID)})
    assert device is not None

    with patch.object(
        FakeSonoffCamera, "test_alarm", return_value=None, autospec=True
    ) as mock_test:
        await hass.services.async_call(
            DOMAIN,
            "trigger_alarm",
            {"device_id": device.id, "duration": 3},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_test.await_args.args[1] == 3
