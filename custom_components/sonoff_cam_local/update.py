"""Update entity reporting OTA firmware availability.

Installing an over-the-air update from Home Assistant has not been verified on
the stock firmware, so the entity is informational only and disabled by default.
"""

from __future__ import annotations

from homeassistant.components.update import UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up the update entity."""
    async_add_entities([SonoffCamFirmwareUpdate(entry.runtime_data)])


class SonoffCamFirmwareUpdate(SonoffCamEntity, UpdateEntity):
    """Report the firmware version and any available update."""

    _attr_translation_key = "firmware"
    _attr_icon = "mdi:package-up"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "firmware")

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed firmware version."""
        info = self.coordinator.device_info
        return info.firmware if info else None

    @property
    def latest_version(self) -> str | None:
        """Return the available firmware version, if any."""
        available = str(self.coordinator.data.ota.get("available_update") or "").strip()
        return available or self.installed_version

    @property
    def release_url(self) -> str | None:
        """Return the changelog URL reported by the camera, if any."""
        url = str(self.coordinator.data.ota.get("changelog_url") or "").strip()
        return url or None

    @property
    def in_progress(self) -> bool:
        """Return whether an OTA update is currently running."""
        status = str(self.coordinator.data.upgrade.get("status") or "").strip().lower()
        return status not in ("", "idle", "stop")

    async def async_install(
        self, version: str | None, *, backup: bool = False, **kwargs: object
    ) -> None:
        """Ask the camera to download and install the available firmware update.

        This triggers the vendor's over-the-air upgrade (``Ota.SetConfig`` with
        ``start: true``). The camera downloads from SONOFF's servers and reboots;
        wrong or interrupted firmware can brick the device.
        """
        config = self.coordinator.data.ota_config.get("config") or {}
        await self.coordinator.async_write(
            self.coordinator.client.start_ota_update(
                auto=bool(config.get("auto")),
                window=str(config.get("time") or "2:00-4:00"),
            )
        )
