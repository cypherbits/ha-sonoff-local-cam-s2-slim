"""Shared entity base for the SONOFF CAM-S2 (Local) integration."""

from __future__ import annotations

from contextlib import suppress

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SonoffCamCoordinator


class SonoffCamEntity(CoordinatorEntity[SonoffCamCoordinator]):
    """Base entity wiring a device registry entry and a unique id."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SonoffCamCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device registry information for the camera."""
        info = self.coordinator.device_info
        device = DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_id)},
            name=self.coordinator.device_name,
            manufacturer=MANUFACTURER,
            model=info.model if info else None,
            sw_version=info.firmware if info else None,
            configuration_url=f"http://{self.coordinator.host}/",
        )
        if info and info.mac:
            with suppress(ValueError):
                device["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(info.mac))}
        return device
