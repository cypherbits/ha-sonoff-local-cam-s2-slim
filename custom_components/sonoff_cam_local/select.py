"""Select entities for the camera's enumerated settings."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any
from zoneinfo import available_timezones

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1

_SelectFn = Callable[[SonoffCamCoordinator, str], Coroutine[Any, Any, Any]]

#: ``NightVision.infraredSetting`` enum baked into the camera's web UI.
NIGHT_VISION_MODES: dict[str, int] = {"auto": 0, "on": 1, "off": 2}
_NIGHT_VISION_BY_VALUE = {value: key for key, value in NIGHT_VISION_MODES.items()}

#: ``Onvif.rtspResolution`` enum (``Me`` in the web UI).
RTSP_RESOLUTIONS = ("1080P", "360P")

#: ``Alarm.soundId`` is undocumented (Alarm is absent from the web bundle); the
#: UI never exposes a list, so offer the observed default family plus whatever
#: the device currently reports.
_ALARM_SOUND_BASE = ("alarm1", "alarm2", "alarm3", "alarm4", "alarm5")


def _alarm_sound_options(coordinator: SonoffCamCoordinator) -> list[str]:
    options = list(_ALARM_SOUND_BASE)
    current = coordinator.data.alarm.sound_id
    if current and current not in options:
        options.append(current)
    return options


@dataclass(frozen=True, kw_only=True)
class SonoffCamSelectDescription(SelectEntityDescription):
    """Description of an enumerated camera setting."""

    value_fn: Callable[[SonoffCamCoordinator], str | None]
    options_fn: Callable[[SonoffCamCoordinator], list[str]]
    select_fn: _SelectFn
    enabled_default: bool = True


SELECTS: tuple[SonoffCamSelectDescription, ...] = (
    SonoffCamSelectDescription(
        key="night_vision_mode",
        value_fn=lambda c: _NIGHT_VISION_BY_VALUE.get(c.data.night_vision.infrared_setting, "auto"),
        options_fn=lambda c: list(NIGHT_VISION_MODES),
        select_fn=lambda c, v: c.client.set_night_vision_mode(NIGHT_VISION_MODES[v]),
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamSelectDescription(
        key="timezone",
        value_fn=lambda c: c.data.timezone_info.get("id"),
        options_fn=lambda c: [],
        select_fn=lambda c, v: c.client.set_timezone(v),
        icon="mdi:map-clock",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamSelectDescription(
        key="rtsp_resolution",
        value_fn=lambda c: c.data.onvif_raw.get("rtspResolution") or RTSP_RESOLUTIONS[0],
        options_fn=lambda c: list(RTSP_RESOLUTIONS),
        select_fn=lambda c, v: c.client.set_rtsp_resolution(v),
        icon="mdi:video-high-definition",
        entity_category=EntityCategory.CONFIG,
    ),
    SonoffCamSelectDescription(
        key="alarm_sound",
        value_fn=lambda c: c.data.alarm.sound_id,
        options_fn=_alarm_sound_options,
        select_fn=lambda c, v: c.client.set_alarm_config(sound=v),
        icon="mdi:music-note",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entities."""
    coordinator = entry.runtime_data
    # ``zoneinfo.available_timezones`` imports tzdata, a blocking call; resolve
    # the list once in an executor instead of inside the entity's options.
    timezones = await hass.async_add_executor_job(_all_timezones)
    async_add_entities(
        SonoffCamSelect(
            coordinator,
            description,
            static_options=timezones if description.key == "timezone" else None,
        )
        for description in SELECTS
    )


def _all_timezones() -> list[str]:
    return sorted(available_timezones())


class SonoffCamSelect(SonoffCamEntity, SelectEntity):
    """An enumerated camera setting."""

    entity_description: SonoffCamSelectDescription

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamSelectDescription,
        *,
        static_options: list[str] | None = None,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._static_options = static_options
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def options(self) -> list[str]:
        """Return the selectable options."""
        if self._static_options is not None:
            return self._static_options
        return self.entity_description.options_fn(self.coordinator)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_select_option(self, option: str) -> None:
        """Write a new option to the camera."""
        await self.coordinator.async_write(
            self.entity_description.select_fn(self.coordinator, option)
        )
