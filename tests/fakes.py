"""Shared fakes that stand in for the vendored sonoff_cam client in tests."""

from __future__ import annotations

from custom_components.sonoff_cam_local.sonoff_cam.exceptions import (
    AuthenticationError,
    ConnectionFailed,
)
from custom_components.sonoff_cam_local.sonoff_cam.models import (
    DeviceInfo,
    MotionConfig,
    ScreenConfig,
)

DEVICE_ID = "sonoffcams2-aa:bb:cc:dd:ee:ff"
PASSWORD = "secret"
RTSP_PASSWORD = "rtsp-secret"

_RAW: dict[str, dict] = {
    "NightVision.GetConfig": {"infraredSetting": 1},
    "Onvif.GetConfig": {"enable": True, "user": "sonoff", "password": RTSP_PASSWORD},
    "LiveStream.GetStatus": {"curViewers": 1},
    "Ota.GetStatus": {"available_update": ""},
    "Ota.GetConfig": {"config": {"auto": False}},
    "WebSocket.GetConfig": {"config": {"enable": False}},
}


class FakeRpc:
    """Minimal stand-in for sonoff_cam.rpc.RpcClient."""

    def __init__(self) -> None:
        self.listeners: list = []

    def add_listener(self, callback) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback) -> None:
        if callback in self.listeners:
            self.listeners.remove(callback)


class FakeSonoffCamera:
    """A successful stand-in for sonoff_cam.SonoffCamera."""

    def __init__(
        self, host, password=None, *, user="admin", port=80, timeout=30.0, ssl=False
    ) -> None:
        self.host = host
        self.password = password
        self.rpc = FakeRpc()

    async def connect(self) -> FakeSonoffCamera:
        return self

    async def close(self) -> None:
        return None

    async def get_device_info(self, refresh=False) -> DeviceInfo:
        return DeviceInfo(
            name="CAM-S2",
            model="SN-CAM-S2-01",
            device_id=DEVICE_ID,
            firmware="2.2.2",
            mac="aa:bb:cc:dd:ee:ff",
            auth_enabled=True,
        )

    async def get_status(self) -> dict:
        if self.password != PASSWORD:
            raise AuthenticationError(401, "bad password")
        return {"uptime": 42, "ram_free": 1234}

    async def get_motion_config(self) -> MotionConfig:
        return MotionConfig(enabled=True, detect_all=True, detect_human=False, sensitivity=2)

    async def get_screen_config(self) -> ScreenConfig:
        return ScreenConfig(watermark_display=True, screen_flip=False)

    async def get_led_config(self) -> dict:
        return {"enable": True}

    async def get_speaker_config(self) -> dict:
        return {"speakerVolume": 50}

    async def get_microphone_config(self) -> dict:
        return {"microphoneVolume": 40}

    async def wifi_status(self) -> dict:
        return {"rssi": -40, "ssid": "home", "curViewers": 0}

    async def raw_call(self, method: str, params=None) -> dict:
        return _RAW.get(method, {})


class UnreachableSonoffCamera(FakeSonoffCamera):
    """A stand-in whose connection always fails."""

    async def connect(self):
        raise ConnectionFailed("host unreachable")
