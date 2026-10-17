"""Diagnostic sensors for the camera."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SonoffCamSensorDescription(SensorEntityDescription):
    """Description of a read-only camera sensor."""

    value_fn: Callable[[SonoffCamCoordinator], Any]
    enabled_default: bool = True


SENSORS: tuple[SonoffCamSensorDescription, ...] = (
    SonoffCamSensorDescription(
        key="wifi_signal",
        value_fn=lambda c: c.data.wifi.get("rssi"),
        icon="mdi:wifi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
    ),
    SonoffCamSensorDescription(
        key="wifi_network",
        value_fn=lambda c: c.data.wifi.get("ssid"),
        icon="mdi:wifi-cog",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SonoffCamSensorDescription(
        key="uptime",
        value_fn=lambda c: c.data.status.get("uptime"),
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SonoffCamSensorDescription(
        key="ram_free",
        value_fn=lambda c: c.data.status.get("ram_free"),
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SonoffCamSensorDescription(
        key="viewers",
        value_fn=lambda c: c.data.live_stream.get("curViewers"),
        icon="mdi:account-eye",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(SonoffCamSensor(coordinator, description) for description in SENSORS)


class SonoffCamSensor(SonoffCamEntity, SensorEntity):
    """A read-only camera sensor."""

    entity_description: SonoffCamSensorDescription

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator)
