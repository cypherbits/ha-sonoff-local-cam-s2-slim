"""Text entities: NTP servers and the local (mDNS) domain name."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1

_SetFn = Callable[[SonoffCamCoordinator, str], Coroutine[Any, Any, Any]]


def _system_config(coordinator: SonoffCamCoordinator) -> dict[str, Any]:
    return dict((coordinator.data.system_config or {}).get("config") or {})


def _set_ntp(coordinator: SonoffCamCoordinator, server: str, *, primary: bool) -> Any:
    config = _system_config(coordinator)
    sntp = dict(config.get("sntp") or {})
    sntp["server1" if primary else "server2"] = server
    config["sntp"] = sntp
    return coordinator.client.set_system_config(config)


def _set_domain(coordinator: SonoffCamCoordinator, domain: str) -> Any:
    config = _system_config(coordinator)
    config["domain"] = domain
    return coordinator.client.set_system_config(config)


@dataclass(frozen=True, kw_only=True)
class SonoffCamTextDescription(TextEntityDescription):
    """Description of a writable text setting."""

    value_fn: Callable[[SonoffCamCoordinator], str | None]
    set_fn: _SetFn
    enabled_default: bool = True


TEXTS: tuple[SonoffCamTextDescription, ...] = (
    SonoffCamTextDescription(
        key="ntp_server1",
        value_fn=lambda c: (c.data.system_config.get("config", {}).get("sntp") or {}).get(
            "server1"
        ),
        set_fn=lambda c, v: _set_ntp(c, v, primary=True),
        icon="mdi:clock-time-four-outline",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTextDescription(
        key="ntp_server2",
        value_fn=lambda c: (c.data.system_config.get("config", {}).get("sntp") or {}).get(
            "server2"
        ),
        set_fn=lambda c, v: _set_ntp(c, v, primary=False),
        icon="mdi:clock-time-four-outline",
        entity_category=EntityCategory.CONFIG,
        enabled_default=False,
    ),
    SonoffCamTextDescription(
        key="local_domain",
        value_fn=lambda c: c.data.system_config.get("config", {}).get("domain"),
        set_fn=_set_domain,
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
    """Set up the text entities."""
    coordinator = entry.runtime_data
    async_add_entities(SonoffCamText(coordinator, description) for description in TEXTS)


class SonoffCamText(SonoffCamEntity, TextEntity):
    """A writable text setting on the camera."""

    entity_description: SonoffCamTextDescription
    _attr_native_max = 253

    def __init__(
        self,
        coordinator: SonoffCamCoordinator,
        description: SonoffCamTextDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def native_value(self) -> str | None:
        """Return the current text value."""
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_value(self, value: str) -> None:
        """Write a new text value."""
        await self.coordinator.async_write(self.entity_description.set_fn(self.coordinator, value))
