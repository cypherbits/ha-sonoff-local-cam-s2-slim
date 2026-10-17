"""Shared fakes that stand in for the vendored sonoff_cam client in tests."""

from __future__ import annotations

from custom_components.sonoff_cam_local.sonoff_cam.exceptions import (
    AuthenticationError,
    ConnectionFailed,
)
from custom_components.sonoff_cam_local.sonoff_cam.models import (
    AlarmConfig,
    DeviceInfo,
    MotionConfig,
    NightVisionConfig,
    ScreenConfig,
)

DEVICE_ID = "sonoffcams2-aa:bb:cc:dd:ee:ff"
PASSWORD = "secret"
RTSP_PASSWORD = "rtsp-secret"

_RAW: dict[str, dict] = {
    "Onvif.GetConfig": {"enable": True, "user": "sonoff", "password": RTSP_PASSWORD},
    "Ota.GetStatus": {"available_update": "", "changelog_url": "", "status": "stop"},
    "Ota.GetConfig": {
        "config": {"auto": False, "query": True, "time": "2:00-4:00", "start": False}
    },
    "WebSocket.GetConfig": {"config": {"enable": False}},
    "Upgrade.GetStatus": {"status": "idle"},
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
        return {
            "uptime": 42,
            "ram_free": 1234,
            "unixtime": 1792010987,
            "ram_size": 43288,
            "ram_min_free": 6732,
            "flash_size": 4,
            "timezone_info": {"id": "Europe/Madrid"},
        }

    async def get_motion_config(self) -> MotionConfig:
        return MotionConfig(enabled=True, detect_all=True, detect_human=False, sensitivity=2)

    async def get_alarm_config(self) -> AlarmConfig:
        return AlarmConfig(enabled=False, duration=10, sound_id="alarm1", on_motion=False)

    async def get_night_vision_config(self) -> NightVisionConfig:
        return NightVisionConfig(infrared_setting=1)

    async def get_system_config(self) -> dict:
        return {
            "config": {
                "sntp": {"server1": "pool.ntp.org", "server2": "time.google.com"},
                "domain": "CAM-S2.local",
                "debug": {"websocket_enable": False},
            }
        }

    async def get_screen_config(self) -> ScreenConfig:
        return ScreenConfig(watermark_display=True, screen_flip=False)

    async def get_led_config(self) -> dict:
        return {"enable": True}

    async def get_speaker_config(self) -> dict:
        return {"speakerVolume": 50}

    async def get_microphone_config(self) -> dict:
        return {"microphoneVolume": 40}

    async def wifi_status(self) -> dict:
        return {"rssi": -40, "ssid": "home", "sta_ip": "192.168.1.100", "ap_client_count": 0}

    async def wifi_config(self) -> dict:
        return {"sta": {"enable": True, "ssid": "home"}, "ap": {}}

    async def get_live_stream_status(self) -> dict:
        return {"maxViewers": 2, "curViewers": 0}

    async def get_websocket_status(self) -> dict:
        return {"connected": False}

    # -- write paths -----------------------------------------------------
    async def set_motion_config(self, config=None, **kwargs) -> MotionConfig:
        return await self.get_motion_config()

    async def set_motion_schedule(self, **kwargs) -> MotionConfig:
        return await self.get_motion_config()

    async def set_alarm_config(self, config=None, **kwargs) -> AlarmConfig:
        return await self.get_alarm_config()

    async def set_alarm_schedule(self, **kwargs) -> AlarmConfig:
        return await self.get_alarm_config()

    async def test_alarm(self, duration: int = 1) -> None:
        return None

    async def set_screen_config(self, config) -> dict:
        return config

    async def set_led_config(self, config) -> dict:
        return config

    async def set_speaker_config(self, config) -> dict:
        return config

    async def set_microphone_config(self, config) -> dict:
        return config

    async def set_night_vision_mode(self, infrared_setting) -> NightVisionConfig:
        return NightVisionConfig(infrared_setting=int(infrared_setting))

    async def set_onvif_config(self, config) -> dict:
        return config

    async def set_rtsp_resolution(self, resolution: str) -> dict:
        return {"rtspResolution": resolution}

    async def set_system_config(self, config) -> dict:
        return config

    async def set_wifi_config(self, ssid, password, *, enable=True) -> dict:
        return {"config": {"sta": {"ssid": ssid}}}

    async def set_timezone(self, timezone_id: str) -> dict:
        return {}

    async def set_time(self, unixtime: int) -> dict:
        return {}

    async def set_ota_config(self, config) -> dict:
        return {}

    async def start_ota_update(self, **kwargs) -> dict:
        return {}

    async def reboot(self) -> dict:
        return {}

    async def factory_reset(self) -> dict:
        return {}

    async def wifi_scan(self) -> dict:
        return {"results": [{"ssid": "home", "rssi": -40, "channel": 6}]}

    async def raw_call(self, method: str, params=None) -> dict:
        return _RAW.get(method, {})


class UnreachableSonoffCamera(FakeSonoffCamera):
    """A stand-in whose connection always fails."""

    async def connect(self):
        raise ConnectionFailed("host unreachable")
