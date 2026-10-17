"""Number entities: sensitivity and audio volumes."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1

_SetFn = Callable[[SonoffCamCoordinator, float], Coroutine[Any, Any, Any]]


@dataclass(frozen=True, kw_only=True)
class SonoffCamNumberDescription(NumberEntityDescription):
    """Description of a numeric camera setting."""

    value_fn: Callable[[SonoffCamCoordinator], float]
    set_fn: _SetFn
    enabled_default: bool = True


NUMBERS: tuple[SonoffCamNumberDescription, ...] = (
    SonoffCamNumberDescription(
        key="motion_sensitivity",
        value_fn=lambda c: c.data.motion.sensitivity,
        set_fn=lambda c, v: c.client.set_motion_config(sensitivity=int(v)),
        icon="mdi:tune-variant",
        native_min_value=0,
        native_max_value=10,
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamNumberDescription(
        key="speaker_volume",
        value_fn=lambda c: float(c.data.speaker.get("speakerVolume", 0) or 0),
        set_fn=lambda c, v: c.client.set_speaker_config(
            {**c.data.speaker, "speakerVolume": int(v)}
        ),
        icon="mdi:volume-high",
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamNumberDescription(
        key="microphone_volume",
        value_fn=lambda c: float(c.data.microphone.get("microphoneVolume", 0) or 0),
        set_fn=lambda c, v: c.client.set_microphone_config(
            {**c.data.microphone, "microphoneVolume": int(v)}
        ),
        icon="mdi:microphone",
        native_min_value=0,
        native_max_value=100,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(SonoffCamNumber(coordinator, description) for description in NUMBERS)


class SonoffCamNumber(SonoffCamEntity, NumberEntity):
    """A numeric camera setting."""

    entity_description: SonoffCamNumberDescription
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamNumberDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value."""
        await self.coordinator.async_write(self.entity_description.set_fn(self.coordinator, value))
