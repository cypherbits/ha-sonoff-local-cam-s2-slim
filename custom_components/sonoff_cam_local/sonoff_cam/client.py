"""High-level async API for the SONOFF CAM-S2.

Example
-------
::

    import asyncio
    from sonoff_cam import SonoffCamera

    async def main():
        async with SonoffCamera("192.168.1.100", password="secret") as cam:
            info = await cam.get_device_info()
            print(info.name, info.model, info.firmware)

            motion = await cam.get_motion_config()
            print("motion enabled:", motion.enabled)

            async for event in cam.events():
                if event.component == "Motion":
                    print("motion detected:", event.event)

    asyncio.run(main())
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

from .exceptions import NotSupported
from .methods import Method
from .models import (
    AlarmConfig,
    CameraEvent,
    DeviceInfo,
    EffectiveSchedule,
    MotionConfig,
    NightVisionConfig,
    OnvifConfig,
    ScreenConfig,
    StatusUpdate,
)
from .rpc import NotificationHandler, RpcClient

MotionLike = Union[MotionConfig, Dict[str, Any], None]


class SonoffCamera:
    """Asynchronous client for one camera.

    Parameters
    ----------
    host:
        Camera IP or hostname.
    password:
        Local admin password. Discovered cameras with ``auth_enabled`` need it
        for every method except ``Sonoff.GetDeviceInfo``.
    """

    def __init__(
        self,
        host: str,
        password: Optional[str] = None,
        *,
        user: str = "admin",
        port: int = 80,
        timeout: float = 30.0,
        ssl: bool = False,
    ) -> None:
        self.host = host
        self.password = password
        self.user = user
        self.rpc = RpcClient(host, password, port=port, user=user, timeout=timeout, ssl=ssl)
        self._device_info: Optional[DeviceInfo] = None

    # ------------------------------------------------------------- lifecycle
    async def connect(self) -> "SonoffCamera":
        await self.rpc.connect()
        return self

    async def close(self) -> None:
        await self.rpc.close()

    async def __aenter__(self) -> "SonoffCamera":
        return await self.connect()

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------ info
    async def get_device_info(self, refresh: bool = False) -> DeviceInfo:
        """Return :class:`DeviceInfo` (cached unless ``refresh=True``)."""
        if self._device_info is None or refresh:
            result = await self.rpc.call(Method.SONOFF_GET_DEVICE_INFO)
            self._device_info = DeviceInfo.from_result(result)
            if self.rpc.device_id is None:
                self.rpc._device_id = self._device_info.device_id  # keep realm in sync
        return self._device_info

    async def get_status(self) -> Dict[str, Any]:
        """``System.GetStatus`` - runtime status dictionary."""
        return await self.rpc.call(Method.SYSTEM_GET_STATUS)

    async def get_system_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.SYSTEM_GET_CONFIG)

    async def set_system_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.SYSTEM_SET_CONFIG, config)

    async def control(self, action: str, value: Any = None) -> Dict[str, Any]:
        """``System.Control`` (e.g. ``action="reboot"``).

        ``value`` is omitted from the payload when ``None``.
        """
        params: Dict[str, Any] = {"action": action}
        if value is not None:
            params["value"] = value
        return await self.rpc.call(Method.SYSTEM_CONTROL, params)

    async def reboot(self) -> Dict[str, Any]:
        return await self.control("reboot")

    async def factory_reset(self) -> Dict[str, Any]:
        """Factory-reset the camera (``System.Control action=factory_reset``)."""
        return await self.control("factory_reset")

    async def set_timezone(self, timezone_id: str) -> Dict[str, Any]:
        """Set the device time zone (``System.SetTimeZone``)."""
        return await self.rpc.call(Method.SYSTEM_SET_TIMEZONE, {"timezone_id": timezone_id})

    async def set_time(self, unixtime: int) -> Dict[str, Any]:
        """Set the device clock from a Unix epoch (``System.SetTime``)."""
        return await self.rpc.call(Method.SYSTEM_SET_TIME, {"unixtime": int(unixtime)})

    # ----------------------------------------------------------------- motion
    async def get_motion_config(self) -> MotionConfig:
        """Motion/AI detection settings (``Motion.GetConfig``)."""
        return MotionConfig.from_result(await self.rpc.call(Method.MOTION_GET_CONFIG))

    async def set_motion_config(
        self,
        config: MotionLike = None,
        *,
        enabled: Optional[bool] = None,
        detect_all: Optional[bool] = None,
        detect_human: Optional[bool] = None,
        sensitivity: Optional[int] = None,
    ) -> MotionConfig:
        """Update motion settings; unspecified fields keep their current value."""
        current = config if isinstance(config, MotionConfig) else await self.get_motion_config()
        params = current.to_params()
        if enabled is not None:
            params["motion_enable"] = enabled
        if detect_all is not None:
            params["type"]["all"] = detect_all
        if detect_human is not None:
            params["type"]["humanoid"] = detect_human
        if sensitivity is not None:
            params["sensitivity"] = sensitivity
        await self.rpc.call(Method.MOTION_SET_CONFIG, params)
        return await self.get_motion_config()

    async def set_motion_enabled(self, enabled: bool) -> MotionConfig:
        return await self.set_motion_config(enabled=enabled)

    async def set_motion_schedule(
        self,
        *,
        enabled: Optional[bool] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: Optional[List[int]] = None,
        all_days: Optional[bool] = None,
    ) -> MotionConfig:
        """Update only the motion ``effective`` schedule (read-modify-write)."""
        current = await self.get_motion_config()
        schedule = current.schedule
        if enabled is not None:
            schedule.enabled = enabled
        if start is not None:
            schedule.start = start
        if end is not None:
            schedule.end = end
        if days is not None:
            schedule.days = list(days)
        if all_days is not None:
            schedule.all_days = all_days
        return await self.set_motion_config(current)

    # ------------------------------------------------------------------ alarm
    async def get_alarm_config(self) -> AlarmConfig:
        """Siren settings (``Alarm.GetConfig``).

        ``Alarm`` is absent from the web bundle; the method was found by probing
        the device. There is no manual trigger -- the siren sounds when it is
        armed and a detector fires. See :class:`~sonoff_cam.models.AlarmConfig`.
        """
        return AlarmConfig.from_result(await self.rpc.call(Method.ALARM_GET_CONFIG))

    async def set_alarm_config(
        self,
        config: Optional[AlarmConfig] = None,
        *,
        enabled: Optional[bool] = None,
        duration: Optional[int] = None,
        sound: Optional[str] = None,
        on_motion: Optional[bool] = None,
        on_person: Optional[bool] = None,
        schedule: Optional[EffectiveSchedule] = None,
    ) -> AlarmConfig:
        """Update the siren settings (read-modify-write: send the whole config)."""
        current = config if isinstance(config, AlarmConfig) else await self.get_alarm_config()
        params = current.to_params()
        if enabled is not None:
            params["enableAlarm"] = 1 if enabled else 0
        if duration is not None:
            params["alarmSetting"]["duration"] = int(duration)
        if sound is not None:
            params["alarmSetting"]["soundId"] = sound
        if on_motion is not None:
            params["moveAlarmType"] = 1 if on_motion else 0
        if on_person is not None:
            params["humanoidAlarmType"] = 1 if on_person else 0
        if schedule is not None:
            params["effective"] = schedule.to_params()
        await self.rpc.call(Method.ALARM_SET_CONFIG, params)
        return await self.get_alarm_config()

    async def set_alarm_schedule(
        self,
        *,
        enabled: Optional[bool] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        days: Optional[List[int]] = None,
        all_days: Optional[bool] = None,
    ) -> AlarmConfig:
        """Update only the alarm ``effective`` schedule (read-modify-write)."""
        current = await self.get_alarm_config()
        schedule = current.schedule
        if enabled is not None:
            schedule.enabled = enabled
        if start is not None:
            schedule.start = start
        if end is not None:
            schedule.end = end
        if days is not None:
            schedule.days = list(days)
        if all_days is not None:
            schedule.all_days = all_days
        return await self.set_alarm_config(current)

    # ------------------------------------------------------------- night vision
    async def get_night_vision_config(self) -> NightVisionConfig:
        return NightVisionConfig.from_result(await self.rpc.call(Method.NIGHT_VISION_GET_CONFIG))

    async def set_night_vision_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.NIGHT_VISION_SET_CONFIG, config)

    async def set_night_vision_mode(self, infrared_setting: int) -> NightVisionConfig:
        """Set the night-vision mode (0 = auto, 1 = always on, 2 = always off)."""
        current = await self.get_night_vision_config()
        current.infrared_setting = int(infrared_setting)
        await self.rpc.call(Method.NIGHT_VISION_SET_CONFIG, current.to_params())
        return await self.get_night_vision_config()

    # ------------------------------------------------------------------ screen
    async def get_screen_config(self) -> ScreenConfig:
        return ScreenConfig.from_result(await self.rpc.call(Method.SCREEN_GET_CONFIG))

    async def set_screen_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.SCREEN_SET_CONFIG, config)

    # ------------------------------------------------------------------- onvif
    async def get_onvif_config(self) -> OnvifConfig:
        return OnvifConfig.from_result(await self.rpc.call(Method.ONVIF_GET_CONFIG))

    async def set_onvif_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.ONVIF_SET_CONFIG, config)

    async def set_rtsp_resolution(self, resolution: str) -> OnvifConfig:
        """Set the RTSP/ONVIF stream resolution (``"1080P"`` or ``"360P"``).

        ``Onvif.SetConfig`` needs the whole payload (user, password, enable and
        rtspResolution), so read-modify-write from the current config.
        """
        current = await self.rpc.call(Method.ONVIF_GET_CONFIG)
        payload = {
            "user": current.get("user", ""),
            "password": current.get("password", ""),
            "enable": current.get("enable", True),
            "rtspResolution": resolution,
        }
        await self.rpc.call(Method.ONVIF_SET_CONFIG, payload)
        return await self.get_onvif_config()

    # ------------------------------------------------------------- status LED
    async def get_led_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.SLED_GET_CONFIG)

    async def set_led_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.SLED_SET_CONFIG, config)

    # ------------------------------------------------------------------ audio
    async def get_speaker_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.SPEAKER_GET_CONFIG)

    async def set_speaker_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.SPEAKER_SET_CONFIG, config)

    async def get_microphone_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.MICROPHONE_GET_CONFIG)

    async def set_microphone_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.MICROPHONE_SET_CONFIG, config)

    # -------------------------------------------------------------------- wifi
    async def wifi_status(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.WIFI_GET_STATUS)

    async def wifi_scan(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.WIFI_SCAN)

    async def wifi_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.WIFI_GET_CONFIG)

    async def set_wifi_config(
        self, ssid: str, password: str, *, enable: bool = True
    ) -> Dict[str, Any]:
        """Join a Wi-Fi network (``WiFi.SetConfig``).

        This drops the camera off its current network and reconnects to ``ssid``;
        if the credentials are wrong the camera becomes unreachable over Wi-Fi.
        """
        payload = {
            "config": {
                "ap": {},
                "sta": {"enable": enable, "ssid": ssid, "pass": password, "ipv4mode": "dhcp"},
            }
        }
        return await self.rpc.call(Method.WIFI_SET_CONFIG, payload)

    # ------------------------------------------------------------- live stream
    async def get_live_stream_status(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.LIVE_STREAM_GET_STATUS)

    # -------------------------------------------------------------- websocket
    async def get_websocket_status(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.WEBSOCKET_GET_STATUS)

    # -------------------------------------------------------------------- ota
    async def get_ota_config(self) -> Dict[str, Any]:
        return await self.rpc.call(Method.OTA_GET_CONFIG)

    async def set_ota_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update OTA settings (``Ota.SetConfig``); ``config`` is merged in full."""
        return await self.rpc.call(Method.OTA_SET_CONFIG, {"config": config})

    async def start_ota_update(self, *, auto: bool = False, window: str = "2:00-4:00") -> Dict[str, Any]:
        """Ask the camera to check for and install a firmware update over the air."""
        return await self.set_ota_config({"query": True, "start": True, "auto": auto, "time": window})

    # ----------------------------------------------------------------- sonoff
    async def set_name(self, name: str) -> Dict[str, Any]:
        """Rename the camera (``Sonoff.SetConfig``)."""
        return await self.rpc.call(Method.SONOFF_SET_CONFIG, {"config": {"name": name}})

    # ------------------------------------------------------------------ events
    async def events(self) -> AsyncIterator[Union[CameraEvent, StatusUpdate]]:
        """Yield device-pushed ``NotifyEvent``/``NotifyStatus`` items.

        Usage::

            async for item in cam.events():
                if isinstance(item, CameraEvent) and item.component == "Motion":
                    ...
        """
        while True:
            message = await self.rpc._queue.get()  # type: ignore[attr-defined]
            for item in self._decode_notification(message):
                yield item

    def on_event(self, handler: Callable[[Union[CameraEvent, StatusUpdate]], Any]) -> Callable:
        """Register a callback; returns a function that removes the listener."""

        def _dispatch(message: Dict[str, Any]) -> None:
            for item in self._decode_notification(message):
                handler(item)

        self.rpc.add_listener(_dispatch)
        return lambda: self.rpc.remove_listener(_dispatch)

    @staticmethod
    def _decode_notification(message: Dict[str, Any]) -> List[Union[CameraEvent, StatusUpdate]]:
        method = message.get("method")
        params = message.get("params") or {}
        if method == Method.NOTIFY_EVENT:
            return list(CameraEvent.from_notification(params))
        if method == Method.NOTIFY_STATUS:
            update = StatusUpdate.from_notification(params)
            return [update] if update is not None else []
        return []

    # --------------------------------------------------------------------- raw
    async def raw_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call any RPC method by name (escape hatch for the whole API surface)."""
        return await self.rpc.call(method, params)

    async def listeners(self) -> List[NotificationHandler]:  # pragma: no cover - introspection
        return list(self.rpc._listeners)  # type: ignore[attr-defined]


__all__ = ["SonoffCamera"]
