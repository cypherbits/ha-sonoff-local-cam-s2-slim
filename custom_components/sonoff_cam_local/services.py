"""Integration services (advanced/dangerous operations)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

SERVICE_SET_WIFI = "set_wifi"

SET_WIFI_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("ssid"): cv.string,
        vol.Required("password"): cv.string,
    }
)


def _entry_for_device(hass: HomeAssistant, device_id: str):
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry
    return None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_WIFI):
        return

    async def _async_set_wifi(call: ServiceCall) -> None:
        entry = _entry_for_device(hass, call.data["device_id"])
        if entry is None:
            raise HomeAssistantError("Device is not a SONOFF CAM-S2 (Local) camera")
        coordinator = entry.runtime_data
        await coordinator.client.set_wifi_config(call.data["ssid"], call.data["password"])

    hass.services.async_register(DOMAIN, SERVICE_SET_WIFI, _async_set_wifi, schema=SET_WIFI_SCHEMA)
