"""Tests for the fake-motion alarm test helper."""

from __future__ import annotations

from typing import Any

from custom_components.sonoff_cam_local.sonoff_cam.client import SonoffCamera
from custom_components.sonoff_cam_local.sonoff_cam.methods import Method


class _StubRpc:
    """Records calls and answers the two reads ``test_alarm`` needs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._reads = {
            Method.ALARM_GET_CONFIG: {
                "enableAlarm": 0,
                "alarmSetting": {"duration": 10, "soundId": "alarm1"},
                "effective": {
                    "enable": 1,
                    "from": "0:0",
                    "to": "0:0",
                    "days": [0, 1, 2, 3, 4, 5, 6],
                    "allDays": 1,
                },
                "moveAlarmType": 0,
                "humanoidAlarmType": 0,
            },
            Method.SCREEN_GET_CONFIG: {"watermarkDisplay": True, "screenFlip": False},
        }

    async def call(self, method: str, params: Any = None) -> dict:
        self.calls.append((method, params))
        read = self._reads.get(method)
        return dict(read) if read is not None else {}


async def test_test_alarm_sequence() -> None:
    """test_alarm arms, fakes motion, then restores the original state."""
    camera = SonoffCamera("192.168.1.100", password="secret")
    camera.rpc = _StubRpc()  # type: ignore[assignment]

    await camera.test_alarm(1)

    methods = [method for method, _ in camera.rpc.calls]
    assert methods == [
        Method.ALARM_GET_CONFIG,
        Method.SCREEN_GET_CONFIG,
        Method.ALARM_SET_CONFIG,
        Method.SCREEN_SET_CONFIG,
        Method.SCREEN_SET_CONFIG,
        Method.ALARM_SET_CONFIG,
    ]

    armed = camera.rpc.calls[2][1]
    assert armed["enableAlarm"] == 1
    assert armed["moveAlarmType"] == 1
    assert armed["humanoidAlarmType"] == 1
    assert armed["alarmSetting"]["duration"] == 1

    assert camera.rpc.calls[3][1]["screenFlip"] is True
    assert camera.rpc.calls[4][1]["screenFlip"] is False

    restored = camera.rpc.calls[5][1]
    assert restored["enableAlarm"] == 0
    assert restored["moveAlarmType"] == 0
    assert restored["alarmSetting"]["duration"] == 10
