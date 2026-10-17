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
    CameraEvent,
    DeviceInfo,
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

    # ------------------------------------------------------------- night vision
    async def get_night_vision_config(self) -> NightVisionConfig:
        return NightVisionConfig.from_result(await self.rpc.call(Method.NIGHT_VISION_GET_CONFIG))

    async def set_night_vision_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self.rpc.call(Method.NIGHT_VISION_SET_CONFIG, config)

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
