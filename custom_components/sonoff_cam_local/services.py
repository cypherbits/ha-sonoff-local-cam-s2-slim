"""Integration services (advanced/dangerous operations)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

SERVICE_SET_WIFI = "set_wifi"
SERVICE_TRIGGER_ALARM = "trigger_alarm"

SET_WIFI_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("ssid"): cv.string,
        vol.Required("password"): cv.string,
    }
)

TRIGGER_ALARM_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("duration", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
    }
)


def _entry_for_device(hass: HomeAssistant, device_id: str) -> ConfigEntry | None:
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry
    return None


def _single_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if len(entries) == 1 else None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services once."""

    async def _async_set_wifi(call: ServiceCall) -> None:
        entry = _entry_for_device(hass, call.data["device_id"])
        if entry is None:
            raise HomeAssistantError("Device is not a SONOFF CAM-S2 (Local) camera")
        await entry.runtime_data.client.set_wifi_config(call.data["ssid"], call.data["password"])

    async def _async_trigger_alarm(call: ServiceCall) -> None:
        device_id = call.data.get("device_id")
        entry = _entry_for_device(hass, device_id) if device_id else _single_entry(hass)
        if entry is None:
            raise HomeAssistantError(
                "Specify a device_id (no single SONOFF CAM-S2 camera could be resolved)"
            )
        coordinator = entry.runtime_data
        await coordinator.async_write(coordinator.client.test_alarm(call.data["duration"]))

    if not hass.services.has_service(DOMAIN, SERVICE_SET_WIFI):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_WIFI, _async_set_wifi, schema=SET_WIFI_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_TRIGGER_ALARM):
        hass.services.async_register(
            DOMAIN, SERVICE_TRIGGER_ALARM, _async_trigger_alarm, schema=TRIGGER_ALARM_SCHEMA
        )
