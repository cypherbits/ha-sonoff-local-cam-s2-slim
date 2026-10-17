"""Device automation triggers for SONOFF CAM-S2 detections."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_DETECTION
from .onvif_events import EVENT_MOTION, EVENT_PERSON

TRIGGER_TYPES: dict[str, str] = {
    "motion_detected": EVENT_MOTION,
    "person_detected": EVENT_PERSON,
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)})


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """Return the detection triggers for a camera device."""
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None or DOMAIN not in device.config_entries:
        return []
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: trigger,
        }
        for trigger in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a detection trigger using the ``sonoff_cam_local_detection`` event."""
    return await event_trigger.async_attach_trigger(
        hass,
        event_trigger.TRIGGER_SCHEMA(
            {
                event_trigger.CONF_PLATFORM: "event",
                event_trigger.CONF_EVENT_TYPE: EVENT_DETECTION,
                event_trigger.CONF_EVENT_DATA: {
                    "device_id": config[CONF_DEVICE_ID],
                    "type": TRIGGER_TYPES[config[CONF_TYPE]],
                },
            }
        ),
        action,
        trigger_info,
        platform_type="device",
    )
