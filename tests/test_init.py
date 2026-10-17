"""Setup tests: the entry creates the expected entities."""

from __future__ import annotations

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

from .fakes import PASSWORD, FakeSonoffCamera


async def test_setup_entry_creates_entities(hass: HomeAssistant) -> None:
    """A full setup wires up the camera, switches and sensors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", FakeSonoffCamera):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data is not None

    assert hass.states.get("camera.cam_s2") is not None
    assert hass.states.get("switch.cam_s2_motion_detection").state == "on"
    assert hass.states.get("switch.cam_s2_status_led").state == "on"
    assert float(hass.states.get("number.cam_s2_speaker_volume").state) == 50
    assert float(hass.states.get("sensor.cam_s2_uptime").state) == 42
    assert float(hass.states.get("sensor.cam_s2_wi_fi_signal").state) == -40
    assert hass.states.get("binary_sensor.cam_s2_motion").state == "off"
    assert hass.states.get("button.cam_s2_reboot") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
