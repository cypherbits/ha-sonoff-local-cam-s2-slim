"""Entity tests for the SONOFF CAM-S2 (Local) integration."""

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


async def test_new_entities_are_created(hass: HomeAssistant) -> None:
    """Alarm, select, sensor and event entities are added."""
    await _setup(hass)

    assert hass.states.get("switch.cam_s2_alarm_armed").state == "off"
    assert float(hass.states.get("number.cam_s2_alarm_duration").state) == 10
    assert hass.states.get("select.cam_s2_night_vision_mode").state == "on"
    assert hass.states.get("select.cam_s2_stream_resolution").state == "1080P"
    assert hass.states.get("sensor.cam_s2_ip_address").state == "192.168.1.100"
    assert hass.states.get("sensor.cam_s2_camera_time") is not None
    assert hass.states.get("event.cam_s2_motion") is not None
    assert hass.states.get("event.cam_s2_person") is not None
    assert hass.states.get("button.cam_s2_scan_wi_fi_networks") is not None
    assert hass.states.get("button.cam_s2_sync_time") is not None
    assert hass.states.get("button.cam_s2_check_for_firmware_update") is not None


async def test_alarm_switch_writes(hass: HomeAssistant) -> None:
    """The alarm switch writes through the read-modify-write client call."""
    await _setup(hass)

    with patch.object(
        FakeSonoffCamera, "set_alarm_config", return_value=None, autospec=True
    ) as mock_set:
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.cam_s2_alarm_armed"}, blocking=True
        )
        await hass.async_block_till_done()

    assert mock_set.await_count == 1
    assert mock_set.await_args.kwargs == {"enabled": True}


async def test_night_vision_select_writes(hass: HomeAssistant) -> None:
    """Selecting a night-vision mode calls the dedicated client method."""
    await _setup(hass)

    with patch.object(
        FakeSonoffCamera, "set_night_vision_mode", return_value=None, autospec=True
    ) as mock_mode:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.cam_s2_night_vision_mode", "option": "off"},
            blocking=True,
        )
        await hass.async_block_till_done()

    # args[0] is the camera instance (autospec), args[1] is the mode value.
    assert mock_mode.await_args.args[1] == 2


async def test_event_entity_fires(hass: HomeAssistant) -> None:
    """A detection bus event updates the matching event entity."""
    await _setup(hass)

    hass.bus.async_fire("sonoff_cam_local_detection", {"device_id": DEVICE_ID, "type": "motion"})
    await hass.async_block_till_done()

    state = hass.states.get("event.cam_s2_motion")
    assert state.attributes.get("event_type") == "motion"
