"""Event entities for motion and person detection (ONVIF push)."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_DETECTION
from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity
from .onvif_events import EVENT_MOTION, EVENT_PERSON

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the motion and person event entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SonoffCamEvent(coordinator, "motion", EVENT_MOTION),
            SonoffCamEvent(coordinator, "person", EVENT_PERSON),
        ]
    )


class SonoffCamEvent(SonoffCamEntity, EventEntity):
    """Fire an event every time a detection starts."""

    _attr_device_class = EventDeviceClass.MOTION

    def __init__(self, coordinator: SonoffCamCoordinator, key: str, kind: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._kind = kind
        self._device_id = coordinator.device_id
        self._attr_event_types = [kind]

    async def async_added_to_hass(self) -> None:
        """Subscribe to the detection bus event for this camera."""
        await super().async_added_to_hass()
        self.async_on_remove(self.hass.bus.async_listen(EVENT_DETECTION, self._handle_detection))

    @callback
    def _handle_detection(self, event: Event) -> None:
        """Record and publish a detection belonging to this camera."""
        if event.data.get("device_id") != self._device_id or event.data.get("type") != self._kind:
            return
        self._trigger_event(self._kind)
        self.async_write_ha_state()
