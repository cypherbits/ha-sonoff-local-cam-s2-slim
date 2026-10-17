"""Diagnostics support: a redacted dump of the camera's readable surface."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from .coordinator import SonoffCamCoordinator
from .sonoff_cam.redact import redact


def _asdict(value: Any) -> Any:
    return asdict(value) if value is not None else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[SonoffCamCoordinator]
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry.

    The camera returns the RTSP and AP passwords in cleartext from
    ``Onvif.GetConfig`` / ``WiFi.GetConfig``; every payload is passed through
    the library's :func:`sonoff_cam.redact.redact` before being handed back.
    """
    coordinator = entry.runtime_data
    data = coordinator.data

    document: dict[str, Any] = {
        "config_entry": {
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get(CONF_PORT),
            "has_admin_password": bool(entry.data.get(CONF_PASSWORD)),
            "options": dict(entry.options),
        },
        "device_info": _asdict(coordinator.device_info),
        "status": data.status,
        "motion": _asdict(data.motion),
        "alarm": _asdict(data.alarm),
        "night_vision": _asdict(data.night_vision),
        "screen": _asdict(data.screen),
        "led": data.led,
        "speaker": data.speaker,
        "microphone": data.microphone,
        "system_config": data.system_config,
        "onvif": data.onvif_raw,
        "wifi": data.wifi,
        "wifi_config": data.wifi_config,
        "live_stream": data.live_stream,
        "ota": data.ota,
        "ota_config": data.ota_config,
        "websocket": data.websocket,
        "websocket_status": data.websocket_status,
        "upgrade": data.upgrade,
    }
    return redact(document)
