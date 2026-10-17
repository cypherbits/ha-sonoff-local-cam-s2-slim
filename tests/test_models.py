"""Round-trip tests for the vendored models."""

from __future__ import annotations

from custom_components.sonoff_cam_local.sonoff_cam.models import (
    AlarmConfig,
    EffectiveSchedule,
    MotionConfig,
    NightVisionConfig,
)


def test_alarm_config_round_trip() -> None:
    """AlarmConfig parses the device payload and serialises it back."""
    raw = {
        "enableAlarm": 1,
        "alarmSetting": {"duration": 5, "soundId": "alarm2"},
        "effective": {
            "enable": 1,
            "from": "0:0",
            "to": "0:0",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "allDays": 1,
        },
        "moveAlarmType": 1,
        "humanoidAlarmType": 0,
    }
    config = AlarmConfig.from_result(raw)
    assert config.enabled is True
    assert config.duration == 5
    assert config.sound_id == "alarm2"
    assert config.on_motion is True
    assert config.on_person is False
    assert config.schedule.all_days is True

    params = config.to_params()
    assert params["enableAlarm"] == 1
    assert params["alarmSetting"] == {"duration": 5, "soundId": "alarm2"}
    assert params["moveAlarmType"] == 1
    assert params["effective"]["allDays"] == 1
    assert params["effective"]["days"] == [0, 1, 2, 3, 4, 5, 6]


def test_motion_config_includes_schedule() -> None:
    """MotionConfig keeps (and re-emits) the ``effective`` schedule."""
    raw = {
        "motion_enable": True,
        "type": {"all": True, "humanoid": False},
        "sensitivity": 3,
        "effective": {
            "enable": 1,
            "from": "00:00",
            "to": "23:45",
            "days": [0, 1],
            "allDays": 0,
        },
    }
    config = MotionConfig.from_result(raw)
    assert config.sensitivity == 3
    assert config.schedule.enabled is True
    assert config.schedule.start == "00:00"
    assert config.schedule.end == "23:45"

    params = config.to_params()
    assert params["effective"]["to"] == "23:45"
    assert params["effective"]["allDays"] == 0


def test_effective_schedule_defaults() -> None:
    """A missing ``effective`` block falls back to safe defaults."""
    schedule = EffectiveSchedule.from_result(None)
    assert schedule.enabled is False
    assert schedule.start == "00:00"
    assert schedule.days == []


def test_night_vision_config() -> None:
    """NightVisionConfig maps the infrared setting to a friendly mode."""
    config = NightVisionConfig.from_result({"infraredSetting": 2})
    assert config.infrared_setting == 2
    assert config.mode == 2
    assert config.to_params() == {
        "infraredSetting": 2,
        "nightVision": 0,
        "lightStrength": 0,
    }
