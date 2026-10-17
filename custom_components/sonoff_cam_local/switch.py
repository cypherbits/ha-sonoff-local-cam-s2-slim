"""Switches exposing the camera's boolean configuration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 0

_SetFn = Callable[[SonoffCamCoordinator, bool], Coroutine[Any, Any, Any]]


def _merge(original: dict[str, Any], **updates: Any) -> dict[str, Any]:
    return {**original, **updates}


def _nested(base: dict[str, Any], section: str, **updates: Any) -> dict[str, Any]:
    return {**base, section: {**(base.get(section) or {}), **updates}}


@dataclass(frozen=True, kw_only=True)
class SonoffCamSwitchDescription(SwitchEntityDescription):
    """Description of a boolean camera setting."""

    value_fn: Callable[[SonoffCamCoordinator], bool]
    set_fn: _SetFn
    enabled_default: bool = True


SWITCHES: tuple[SonoffCamSwitchDescription, ...] = (
    SonoffCamSwitchDescription(
        key="motion_detection",
        value_fn=lambda c: c.data.motion.enabled,
        set_fn=lambda c, v: c.client.set_motion_config(enabled=v),
        icon="mdi:motion-sensor",
    ),
    SonoffCamSwitchDescription(
        key="person_detection",
        value_fn=lambda c: c.data.motion.detect_human,
        set_fn=lambda c, v: c.client.set_motion_config(detect_human=v),
        icon="mdi:account-search",
    ),
    SonoffCamSwitchDescription(
        key="detect_all_motion",
        value_fn=lambda c: c.data.motion.detect_all,
        set_fn=lambda c, v: c.client.set_motion_config(detect_all=v),
        icon="mdi:waveform",
        enabled_default=False,
    ),
    SonoffCamSwitchDescription(
        key="status_led",
        value_fn=lambda c: bool(c.data.led.get("enable")),
        set_fn=lambda c, v: c.client.set_led_config(_merge(c.data.led, enable=v)),
        icon="mdi:led-on",
    ),
    SonoffCamSwitchDescription(
        key="night_vision",
        value_fn=lambda c: bool(c.data.night_vision.get("infraredSetting")),
        set_fn=lambda c, v: c.client.set_night_vision_config(
            _merge(c.data.night_vision, infraredSetting=1 if v else 0)
        ),
        icon="mdi:weather-night",
    ),
    SonoffCamSwitchDescription(
        key="watermark",
        value_fn=lambda c: c.data.screen.watermark_display,
        set_fn=lambda c, v: c.client.set_screen_config(
            _merge(c.data.screen.raw, watermarkDisplay=v)
        ),
        icon="mdi:watermark",
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamSwitchDescription(
        key="screen_flip",
        value_fn=lambda c: c.data.screen.screen_flip,
        set_fn=lambda c, v: c.client.set_screen_config(_merge(c.data.screen.raw, screenFlip=v)),
        icon="mdi:flip-horizontal",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamSwitchDescription(
        key="onvif",
        value_fn=lambda c: c.data.onvif.enabled,
        set_fn=lambda c, v: c.client.set_onvif_config(_merge(c.data.onvif_raw, enable=v)),
        icon="mdi:access-point-network",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamSwitchDescription(
        key="auto_update",
        value_fn=lambda c: bool((c.data.ota_config.get("config") or {}).get("auto")),
        set_fn=lambda c, v: c.client.raw_call(
            "Ota.SetConfig", _nested(c.data.ota_config, "config", auto=v)
        ),
        icon="mdi:update",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamSwitchDescription(
        key="websocket_client",
        value_fn=lambda c: bool((c.data.websocket.get("config") or {}).get("enable")),
        set_fn=lambda c, v: c.client.raw_call(
            "WebSocket.SetConfig", _nested(c.data.websocket, "config", enable=v)
        ),
        icon="mdi:web",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(SonoffCamSwitch(coordinator, description) for description in SWITCHES)


class SonoffCamSwitch(SonoffCamEntity, SwitchEntity):
    """A boolean camera setting."""

    entity_description: SonoffCamSwitchDescription

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamSwitchDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def is_on(self) -> bool:
        """Return the current value of the setting."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the setting."""
        await self.coordinator.async_write(self.entity_description.set_fn(self.coordinator, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the setting."""
        await self.coordinator.async_write(self.entity_description.set_fn(self.coordinator, False))
