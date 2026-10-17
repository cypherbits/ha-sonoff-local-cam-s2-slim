"""Time entities: motion/alarm schedules and the OTA window."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1

_SetFn = Callable[[SonoffCamCoordinator, time], Coroutine[Any, Any, Any]]


def _parse(value: Any) -> time | None:
    """Parse ``"HH:MM"`` / ``"H:MM"`` into a :class:`datetime.time`."""
    if not value:
        return None
    text = str(value).strip()
    if ":" not in text:
        return None
    hour, _, minute = text.partition(":")
    try:
        return time(hour=int(hour), minute=int(minute))
    except ValueError:
        return None


def _fmt(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _ota_parts(time_str: Any) -> tuple[time, time]:
    """Split the OTA ``"2:00-4:00"`` window into two times with fallbacks."""
    start = end = None
    if isinstance(time_str, str) and "-" in time_str:
        left, _, right = time_str.partition("-")
        start, end = _parse(left), _parse(right)
    return start or time(2, 0), end or time(4, 0)


def _set_ota_edge(coordinator: SonoffCamCoordinator, value: time, *, start: bool) -> Coroutine:
    config = dict(coordinator.data.ota_config.get("config") or {})
    current_start, current_end = _ota_parts(config.get("time"))
    begin = value if start else current_start
    finish = current_end if start else value
    config["time"] = f"{_fmt(begin)}-{_fmt(finish)}"
    return coordinator.client.set_ota_config(config)


@dataclass(frozen=True, kw_only=True)
class SonoffCamTimeDescription(TimeEntityDescription):
    """Description of a writable time setting."""

    value_fn: Callable[[SonoffCamCoordinator], time | None]
    set_fn: _SetFn
    enabled_default: bool = True


TIMES: tuple[SonoffCamTimeDescription, ...] = (
    SonoffCamTimeDescription(
        key="motion_schedule_start",
        value_fn=lambda c: _parse(c.data.motion.schedule.start),
        set_fn=lambda c, v: c.client.set_motion_schedule(start=_fmt(v)),
        icon="mdi:calendar-arrow-right",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTimeDescription(
        key="motion_schedule_end",
        value_fn=lambda c: _parse(c.data.motion.schedule.end),
        set_fn=lambda c, v: c.client.set_motion_schedule(end=_fmt(v)),
        icon="mdi:calendar-arrow-left",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTimeDescription(
        key="alarm_schedule_start",
        value_fn=lambda c: _parse(c.data.alarm.schedule.start),
        set_fn=lambda c, v: c.client.set_alarm_schedule(start=_fmt(v)),
        icon="mdi:calendar-arrow-right",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTimeDescription(
        key="alarm_schedule_end",
        value_fn=lambda c: _parse(c.data.alarm.schedule.end),
        set_fn=lambda c, v: c.client.set_alarm_schedule(end=_fmt(v)),
        icon="mdi:calendar-arrow-left",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTimeDescription(
        key="ota_window_start",
        value_fn=lambda c: _ota_parts((c.data.ota_config.get("config") or {}).get("time"))[0],
        set_fn=lambda c, v: _set_ota_edge(c, v, start=True),
        icon="mdi:update",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTimeDescription(
        key="ota_window_end",
        value_fn=lambda c: _ota_parts((c.data.ota_config.get("config") or {}).get("time"))[1],
        set_fn=lambda c, v: _set_ota_edge(c, v, start=False),
        icon="mdi:update",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the time entities."""
    coordinator = entry.runtime_data
    async_add_entities(SonoffCamTime(coordinator, description) for description in TIMES)


class SonoffCamTime(SonoffCamEntity, TimeEntity):
    """A writable time setting on the camera."""

    entity_description: SonoffCamTimeDescription

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamTimeDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def native_value(self) -> time | None:
        """Return the current time value."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_value(self, value: time) -> None:
        """Write a new time value."""
        await self.coordinator.async_write(self.entity_description.set_fn(self.coordinator, value))
