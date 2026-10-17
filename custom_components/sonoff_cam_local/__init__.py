"""SONOFF CAM-S2 / CAM Slim Gen2 local integration.

Talks directly to the camera's stock-firmware WebSocket JSON-RPC service and,
for real-time motion/person events, to its ONVIF PullPoint endpoint. No cloud
and no eWeLink account are required.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN  # noqa: F401  (re-exported for convenience)
from .coordinator import SonoffCamCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
    Platform.UPDATE,
]

type SonoffCamConfigEntry = ConfigEntry[SonoffCamCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SonoffCamConfigEntry) -> bool:
    """Set up a config entry."""
    await async_setup_services(hass)

    coordinator = SonoffCamCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_shutdown)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonoffCamConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
