"""Tests for the read-modify-write helpers in the camera client."""

from __future__ import annotations

from typing import Any

from custom_components.sonoff_cam_local.sonoff_cam.client import SonoffCamera
from custom_components.sonoff_cam_local.sonoff_cam.methods import Method


class _StubRpc:
    """Record calls and answer reads from a fixed dictionary."""

    def __init__(self, reads: dict[str, Any]) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._reads = reads

    async def call(self, method: str, params: Any = None) -> dict:
        self.calls.append((method, params))
        return dict(self._reads.get(method) or {})


def _camera(reads: dict[str, Any]) -> tuple[SonoffCamera, _StubRpc]:
    camera = SonoffCamera("192.168.1.100", password="secret")
    stub = _StubRpc(reads)
    camera.rpc = stub  # type: ignore[assignment]
    return camera, stub


async def test_set_system_config_wraps_config() -> None:
    """System.SetConfig receives the same {"config": ...} shape as GetConfig."""
    camera, stub = _camera({})
    await camera.set_system_config({"domain": "cam.local"})
    assert stub.calls[-1] == (Method.SYSTEM_SET_CONFIG, {"config": {"domain": "cam.local"}})


async def test_set_onvif_enabled_preserves_credentials() -> None:
    """Toggling ONVIF must not erase the RTSP username/password or resolution."""
    camera, stub = _camera(
        {
            Method.ONVIF_GET_CONFIG: {
                "enable": True,
                "user": "sonoff",
                "password": "secret",
                "rtspResolution": "360P",
                "readOnly": "ignored",
            }
        }
    )
    await camera.set_onvif_enabled(False)
    payload = stub.calls[-2][1]
    assert payload == {
        "enable": False,
        "user": "sonoff",
        "password": "secret",
        "rtspResolution": "360P",
    }


async def test_set_screen_fields_preserves_other_fields() -> None:
    """Screen.SetConfig starts from the fresh config and only changes the field."""
    camera, stub = _camera(
        {
            Method.SCREEN_GET_CONFIG: {
                "watermarkDisplay": True,
                "screenFlip": False,
                "extra": "keep",
            }
        }
    )
    await camera.set_screen_fields(screenFlip=True)
    payload = stub.calls[-1][1]
    assert payload == {
        "watermarkDisplay": True,
        "screenFlip": True,
        "extra": "keep",
    }


async def test_set_ota_window_preserves_other_ota_fields() -> None:
    """Changing one edge of the OTA window keeps the other edge and auto."""
    camera, stub = _camera(
        {
            Method.OTA_GET_CONFIG: {
                "config": {"time": "2:00-4:00", "auto": True, "query": False}
            }
        }
    )
    await camera.set_ota_window(start="01:00")
    payload = stub.calls[-1][1]
    assert payload == {
        "config": {"time": "01:00-4:00", "auto": True, "query": False}
    }


async def test_set_wifi_config_matches_web_ui_payload() -> None:
    """Joining a network sends the same payload as the camera web console."""
    camera, stub = _camera({})
    await camera.set_wifi_config("NewNet", "pw")
    payload = stub.calls[-1][1]
    assert payload == {
        "config": {
            "ap": {},
            "sta": {
                "enable": True,
                "ssid": "NewNet",
                "pass": "pw",
                "ipv4mode": "dhcp",
            },
        }
    }
