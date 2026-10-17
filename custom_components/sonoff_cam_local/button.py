"""Button entities (reboot, Wi-Fi scan, time sync, firmware check, factory reset)."""

from __future__ import annotations

import logging
import time

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import SonoffCamCoordinator
from .entity import SonoffCamEntity

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)

#: Bus event fired with the results of a Wi-Fi scan.
EVENT_WIFI_SCAN = f"{DOMAIN}_wifi_scan"

#: Default siren duration (seconds) when testing the alarm.
TEST_ALARM_DURATION = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[SonoffCamCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SonoffCamRebootButton(coordinator),
            SonoffCamTestAlarmButton(coordinator),
            SonoffCamScanWifiButton(coordinator),
            SonoffCamSyncTimeButton(coordinator),
            SonoffCamCheckFirmwareButton(coordinator),
            SonoffCamFactoryResetButton(coordinator),
        ]
    )


class _SonoffCamButton(SonoffCamEntity, ButtonEntity):
    """Base class for the camera's button entities."""

    entity_description: ButtonEntityDescription

    def __init__(self, coordinator: SonoffCamCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key


class SonoffCamRebootButton(_SonoffCamButton):
    """Restart the camera."""

    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        """Reboot the camera."""
        await self.coordinator.async_write(self.coordinator.client.reboot())


class SonoffCamTestAlarmButton(_SonoffCamButton):
    """Sound the siren once by faking a detection (disabled by default)."""

    _attr_icon = "mdi:alarm-light-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "test_alarm")

    async def async_press(self) -> None:
        """Arm the alarm, fake motion, and restore the config afterwards."""
        await self.coordinator.async_write(self.coordinator.client.test_alarm(TEST_ALARM_DURATION))


class SonoffCamScanWifiButton(_SonoffCamButton):
    """Scan for nearby Wi-Fi networks and publish the results on the bus."""

    _attr_icon = "mdi:wifi-sync"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "scan_wifi")

    async def async_press(self) -> None:
        """Run ``WiFi.Scan`` and fire the results as an event."""
        result = await self.coordinator.client.wifi_scan()
        networks = result.get("results", []) if isinstance(result, dict) else []
        _LOGGER.debug("Wi-Fi scan found %d networks", len(networks))
        self.hass.bus.async_fire(
            EVENT_WIFI_SCAN, {"device_id": self.coordinator.device_id, "networks": networks}
        )


class SonoffCamSyncTimeButton(_SonoffCamButton):
    """Set the camera clock from Home Assistant's clock."""

    _attr_icon = "mdi:clock-check"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "sync_time")

    async def async_press(self) -> None:
        """Write the current time to the camera."""
        await self.coordinator.async_write(self.coordinator.client.set_time(int(time.time())))


class SonoffCamCheckFirmwareButton(_SonoffCamButton):
    """Ask the camera to check for a firmware update (without installing)."""

    _attr_icon = "mdi:cloud-download-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "check_firmware")

    async def async_press(self) -> None:
        """Trigger an OTA check and refresh the update entity."""
        config = dict((self.coordinator.data.ota_config or {}).get("config") or {})
        config["query"] = True
        config.setdefault("start", False)
        await self.coordinator.async_write(self.coordinator.client.set_ota_config(config))


class SonoffCamFactoryResetButton(_SonoffCamButton):
    """Factory-reset the camera (destructive; disabled by default)."""

    _attr_icon = "mdi:restore-alert"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SonoffCamCoordinator) -> None:
        super().__init__(coordinator, "factory_reset")

    async def async_press(self) -> None:
        """Factory-reset the camera."""
        await self.coordinator.async_write(self.coordinator.client.factory_reset())
