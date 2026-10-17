"""Binary sensors for motion and person detection (ONVIF PullPoint)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the motion and person binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SonoffCamDetectionSensor(coordinator, "motion"),
            SonoffCamDetectionSensor(coordinator, "person"),
        ]
    )


class SonoffCamDetectionSensor(SonoffCamEntity, BinarySensorEntity):
    """A motion or AI person-detection state pushed over ONVIF."""

    def __init__(self, coordinator: SonoffCamCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._key = key
        self._attr_device_class = (
            BinarySensorDeviceClass.OCCUPANCY if key == "person" else BinarySensorDeviceClass.MOTION
        )

    @property
    def is_on(self) -> bool:
        """Return whether the detection is currently active."""
        if self._key == "person":
            return self.coordinator.person_active
        return self.coordinator.motion_active
