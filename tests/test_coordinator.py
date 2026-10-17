"""Coordinator tests for the SONOFF CAM-S2 (Local) integration."""

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
from custom_components.sonoff_cam_local.coordinator import SonoffCamCoordinator
from custom_components.sonoff_cam_local.sonoff_cam.models import OnvifConfig

from .fakes import DEVICE_ID, RTSP_PASSWORD, FakeSonoffCamera


async def test_coordinator_fetch(hass: HomeAssistant) -> None:
    """The coordinator parses the readable surface into typed data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: "secret"},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", FakeSonoffCamera):
        coordinator = SonoffCamCoordinator(hass, entry)
        await coordinator._async_setup()
        data = await coordinator._async_update_data()

    assert coordinator.device_id == DEVICE_ID
    assert coordinator.rtsp_url == (
        f"rtsp://sonoff:{RTSP_PASSWORD}@192.168.1.100:554/av_stream/ch0"
    )
    assert data.motion.enabled is True
    assert data.motion.sensitivity == 2
    assert data.wifi["rssi"] == -40
    assert OnvifConfig.from_result(data.onvif_raw).enabled is True
    assert data.status["uptime"] == 42

    await coordinator.async_shutdown()
