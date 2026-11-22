"""Data update coordinator for the SONOFF CAM-S2 (Local) integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_RPC_USERNAME,
    DEFAULT_RTSP_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DETECTION_TIMEOUT,
    DOMAIN,
    EVENT_DETECTION,
    ONVIF_PORT,
    RTSP_PORT,
    RTSP_STREAM_PATH,
)
from .onvif_events import EVENT_MOTION, EVENT_PERSON, OnvifEventClient
from .sonoff_cam import SonoffCamera
from .sonoff_cam.exceptions import (
    AuthenticationError,
    ConnectionFailed,
    NotSupported,
    ProtocolError,
    RpcError,
    SonoffCamError,
    Timeout,
)
from .sonoff_cam.models import (
    AlarmConfig,
    DeviceInfo,
    MotionConfig,
    NightVisionConfig,
    OnvifConfig,
    ScreenConfig,
)

if TYPE_CHECKING:
    from . import SonoffCamConfigEntry

_LOGGER = logging.getLogger(__name__)

#: Errors that mean "the device is unreachable right now" -> retry later.
_TRANSIENT_ERRORS = (ConnectionFailed, Timeout, ProtocolError, RpcError, OSError)


@dataclass
class SonoffCamData:
    """Everything the coordinator has fetched in one poll cycle."""

    status: dict[str, Any] = field(default_factory=dict)
    motion: MotionConfig = field(default_factory=MotionConfig)
    alarm: AlarmConfig = field(default_factory=AlarmConfig)
    night_vision: NightVisionConfig = field(default_factory=NightVisionConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    led: dict[str, Any] = field(default_factory=dict)
    speaker: dict[str, Any] = field(default_factory=dict)
    microphone: dict[str, Any] = field(default_factory=dict)
    onvif: OnvifConfig = field(default_factory=OnvifConfig)
    onvif_raw: dict[str, Any] = field(default_factory=dict)
    system_config: dict[str, Any] = field(default_factory=dict)
    timezone_info: dict[str, Any] = field(default_factory=dict)
    wifi: dict[str, Any] = field(default_factory=dict)
    wifi_config: dict[str, Any] = field(default_factory=dict)
    live_stream: dict[str, Any] = field(default_factory=dict)
    ota: dict[str, Any] = field(default_factory=dict)
    ota_config: dict[str, Any] = field(default_factory=dict)
    websocket: dict[str, Any] = field(default_factory=dict)
    websocket_status: dict[str, Any] = field(default_factory=dict)
    upgrade: dict[str, Any] = field(default_factory=dict)


class SonoffCamCoordinator(DataUpdateCoordinator[SonoffCamData]):
    """Poll the camera over its local WebSocket JSON-RPC service."""

    config_entry: SonoffCamConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SonoffCamConfigEntry) -> None:
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
        self._write_lock = asyncio.Lock()

        self.client = SonoffCamera(
            self.host,
            entry.data.get(CONF_PASSWORD),
            user=DEFAULT_RPC_USERNAME,
            port=self.port,
            timeout=20.0,
        )

        self.device_info: DeviceInfo | None = None
        self.rtsp_username: str = entry.data.get(CONF_RTSP_USERNAME) or DEFAULT_RTSP_USERNAME
        self.rtsp_password: str = entry.data.get(CONF_RTSP_PASSWORD, "")
        self.rtsp_url: str = ""

        self.motion_active = False
        self.person_active = False
        self._detection_timers: dict[str, CALLBACK_TYPE] = {}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {self.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    # ------------------------------------------------------------------ setup
    async def _async_setup(self) -> None:
        """Connect, read identity and resolve the RTSP credentials once."""
        try:
            await self.client.connect()
            self.device_info = await self.client.get_device_info(refresh=True)
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Authentication with the camera failed; update the password"
            ) from err
        except SonoffCamError as err:
            raise ConfigEntryNotReady(
                f"Could not reach camera at {self.host}: {err}"
            ) from err

        if not self.rtsp_password:
            try:
                onvif = await self.client.raw_call("Onvif.GetConfig")
                self.rtsp_username = onvif.get("user") or self.rtsp_username
                self.rtsp_password = onvif.get("password") or ""
            except SonoffCamError as err:
                _LOGGER.debug("Could not read ONVIF/RTSP credentials: %s", err)

        self.rtsp_url = _build_rtsp_url(self.host, self.rtsp_username, self.rtsp_password)

        self.client.rpc.add_listener(self._handle_rpc_notification)
        self.entry.async_on_unload(
            lambda: self.client.rpc.remove_listener(self._handle_rpc_notification)
        )

        if self.entry.options.get(CONF_ENABLE_ONVIF, True) and self.rtsp_password:
            client = OnvifEventClient(
                self.host,
                self.rtsp_username,
                self.rtsp_password,
                self._handle_onvif_event,
                port=ONVIF_PORT,
            )
            self.entry.async_create_background_task(
                self.hass, client.async_run(), name=f"{DOMAIN}-onvif-events"
            )

    async def async_shutdown(self) -> None:
        """Close connections and stop pending timers when the entry unloads."""
        for unsub in self._detection_timers.values():
            unsub()
        self._detection_timers.clear()
        await super().async_shutdown()
        await self.client.close()

    # ------------------------------------------------------------------ fetch
    async def _async_update_data(self) -> SonoffCamData:
        try:
            return await self._fetch_all()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Authentication with the camera failed; update the password"
            ) from err
        except _TRANSIENT_ERRORS as err:
            raise UpdateFailed(f"Could not reach camera at {self.host}: {err}") from err

    async def _fetch_all(self) -> SonoffCamData:
        data = SonoffCamData()
        # System.GetStatus is the primary liveness check: let a failure mark
        # the whole poll as failed instead of silently publishing empty data.
        data.status = await self.client.get_status()
        data.timezone_info = data.status.get("timezone_info") or {}
        data.motion = await self._safe(self.client.get_motion_config(), MotionConfig())
        data.alarm = await self._safe(self.client.get_alarm_config(), AlarmConfig())
        data.night_vision = await self._safe(
            self.client.get_night_vision_config(), NightVisionConfig()
        )
        data.screen = await self._safe(self.client.get_screen_config(), ScreenConfig())
        data.led = await self._safe(self.client.get_led_config())
        data.speaker = await self._safe(self.client.get_speaker_config())
        data.microphone = await self._safe(self.client.get_microphone_config())
        data.onvif_raw = await self._safe(self.client.raw_call("Onvif.GetConfig"))
        data.onvif = OnvifConfig.from_result(data.onvif_raw)
        data.system_config = await self._safe(self.client.get_system_config())
        data.wifi = await self._safe(self.client.wifi_status())
        data.wifi_config = await self._safe(self.client.wifi_config())
        data.live_stream = await self._safe(self.client.get_live_stream_status())
        data.ota = await self._safe(self.client.raw_call("Ota.GetStatus"))
        data.ota_config = await self._safe(self.client.raw_call("Ota.GetConfig"))
        data.websocket = await self._safe(self.client.raw_call("WebSocket.GetConfig"))
        data.websocket_status = await self._safe(self.client.get_websocket_status())
        data.upgrade = await self._safe(self.client.raw_call("Upgrade.GetStatus"))
        return data

    async def _safe(self, coro: Any, default: Any = None) -> Any:
        """Await a read, tolerating a missing/unsupported method but not auth."""
        try:
            return await coro
        except AuthenticationError:
            raise
        except (NotSupported, RpcError) as err:
            _LOGGER.debug("Optional read failed: %s", err)
            return {} if default is None else default

    # ------------------------------------------------------------------ write
    async def async_write(self, coro: Any) -> Any:
        """Serialise a mutating RPC call and refresh afterwards."""
        async with self._write_lock:
            result = await coro
        await self.async_request_refresh()
        return result

    # --------------------------------------------------------------- push RPC
    @callback
    def _handle_rpc_notification(self, message: dict[str, Any]) -> None:
        """React to device-pushed notifications (best effort).

        The RPC push stream has never been observed delivering data on stock
        firmware, so this is a bonus path; ONVIF is the reliable source.
        """
        if message.get("method") != "NotifyEvent":
            return
        for event in (message.get("params") or {}).get("events", []) or []:
            component = str(event.get("component", ""))
            name = str(event.get("event", "")).lower()
            if component != "Motion":
                continue
            if not any(token in name for token in ("mot", "human", "person")):
                continue
            kind = (
                EVENT_PERSON
                if any(token in name for token in ("human", "person"))
                else EVENT_MOTION
            )
            state = not any(
                token in name for token in ("stop", "end", "false", "clear", "no_")
            )
            self._set_active(kind, state)

    # ------------------------------------------------------------- push ONVIF
    @callback
    def _handle_onvif_event(self, kind: str, state: bool) -> None:
        self._set_active(kind, state)

    def _set_active(self, kind: str, state: bool) -> None:
        changed = False
        if kind == EVENT_MOTION and self.motion_active != state:
            self.motion_active = state
            changed = True
        elif kind == EVENT_PERSON and self.person_active != state:
            self.person_active = state
            changed = True

        if state:
            # Re-arm the safety timer on every "on" event. A lost "off"
            # event must not leave the binary sensor on forever.
            self._cancel_detection_timer(kind)
            self._detection_timers[kind] = async_call_later(
                self.hass,
                DETECTION_TIMEOUT,
                lambda _now: self._detection_expired(kind),
            )
        else:
            self._cancel_detection_timer(kind)

        if changed:
            self.async_update_listeners()
        if changed and state and kind in (EVENT_MOTION, EVENT_PERSON):
            self.hass.bus.async_fire(
                EVENT_DETECTION,
                {
                    "device_id": self.ha_device_id,
                    "native_device_id": self.device_id,
                    "type": kind,
                },
            )

    def _cancel_detection_timer(self, kind: str) -> None:
        if unsub := self._detection_timers.pop(kind, None):
            unsub()

    def _detection_expired(self, kind: str) -> None:
        self._detection_timers.pop(kind, None)
        self._set_active(kind, False)

    # ------------------------------------------------------------- device info
    @property
    def device_id(self) -> str:
        return self.device_info.device_id if self.device_info else self.host

    @property
    def ha_device_id(self) -> str:
        """Return the Home Assistant device-registry id for this camera."""
        registry = dr.async_get(self.hass)
        identifier = (DOMAIN, self.device_id)
        if hasattr(registry, "async_get_devices"):
            devices = registry.async_get_devices(identifiers={identifier})
            return devices[0].id if devices else self.device_id
        device = registry.async_get_device(identifiers={identifier})
        return device.id if device else self.device_id

    @property
    def device_name(self) -> str:
        if self.device_info and self.device_info.name:
            return self.device_info.name
        return f"CAM-S2 {self.host}"


def _build_rtsp_url(host: str, username: str, password: str) -> str:
    auth = ""
    if username:
        user = quote(username, safe="")
        auth = f"{user}:{quote(password, safe='')}@" if password else f"{user}@"
    return f"rtsp://{auth}{host}:{RTSP_PORT}{RTSP_STREAM_PATH}"
