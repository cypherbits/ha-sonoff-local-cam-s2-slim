"""Button entities (reboot)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button entities."""
    async_add_entities([SonoffCamRebootButton(entry.runtime_data)])


class SonoffCamRebootButton(SonoffCamEntity, ButtonEntity):
    """Restart the camera."""

    _attr_translation_key = "reboot"
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        """Reboot the camera."""
        await self.coordinator.async_write(self.coordinator.client.reboot())
