"""Tests for the motion/person device triggers."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DOMAIN,
    EVENT_DETECTION,
)
from custom_components.sonoff_cam_local.device_trigger import (
    async_attach_trigger,
    async_get_triggers,
)

from .fakes import DEVICE_ID, PASSWORD, FakeSonoffCamera


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD},
        options={CONF_ENABLE_ONVIF: False},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.sonoff_cam_local.coordinator.SonoffCamera",
        FakeSonoffCamera,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_device_triggers_are_listed(hass: HomeAssistant) -> None:
    """The camera device exposes both detection triggers."""
    entry = await _setup(hass)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry.entry_id
    )
    assert device is not None

    triggers = await async_get_triggers(hass, device.id)
    assert {trigger["type"] for trigger in triggers} == {
        "motion_detected",
        "person_detected",
    }


async def test_device_trigger_fires_on_detection(hass: HomeAssistant) -> None:
    """The event payload uses the HA device id, so the trigger matches."""
    entry = await _setup(hass)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry.entry_id
    )
    assert device is not None

    fired: list[dict[str, Any]] = []

    async def action(
        run_variables: dict[str, Any], context: Context | None = None
    ) -> None:
        fired.append(run_variables)

    trigger_info: TriggerInfo = {
        "domain": DOMAIN,
        "name": "test",
        "variables": {},
        "trigger_data": {"id": "0", "idx": "0", "alias": None},
    }
    unsub = await async_attach_trigger(
        hass,
        {
            "platform": "device",
            "domain": DOMAIN,
            "device_id": device.id,
            "type": "motion_detected",
        },
        action,
        trigger_info,
    )

    hass.bus.async_fire(
        EVENT_DETECTION,
        {
            "device_id": device.id,
            "native_device_id": DEVICE_ID,
            "type": "motion",
        },
    )
    await hass.async_block_till_done()
    unsub()

    assert fired


async def test_coordinator_emits_registry_device_id(hass: HomeAssistant) -> None:
    """The coordinator publishes the HA registry id used by device triggers."""
    entry = await _setup(hass)
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry.entry_id
    )
    assert device is not None
    coordinator = entry.runtime_data

    events: list[dict[str, Any]] = []
    hass.bus.async_listen(EVENT_DETECTION, lambda event: events.append(event.data))

    coordinator._set_active("motion", True)
    await hass.async_block_till_done()

    assert events
    assert events[0]["device_id"] == device.id
    assert events[0]["native_device_id"] == DEVICE_ID

    coordinator._set_active("motion", False)
    await hass.async_block_till_done()
