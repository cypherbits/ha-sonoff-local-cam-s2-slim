"""Typed models returned by the camera.

Every model keeps the raw ``dict`` under :attr:`raw` so nothing discovered on
the wire is ever lost, while exposing the fields known from the web UI bundle as
attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass
class DeviceInfo:
    """Result of ``Sonoff.GetDeviceInfo``."""

    name: str = ""
    model: str = ""
    device_id: str = ""
    firmware: str = ""
    ip: str = ""
    mac: str = ""
    auth_enabled: bool = False
    auth_domain: Optional[str] = None
    initial_password: bool = False
    connect_with_ap: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "DeviceInfo":
        result = _as_dict(result)
        return cls(
            name=result.get("name", ""),
            model=result.get("model", ""),
            device_id=result.get("id", ""),
            firmware=result.get("ver", ""),
            ip=result.get("ip", ""),
            mac=result.get("mac", ""),
            auth_enabled=bool(result.get("auth_en", False)),
            auth_domain=result.get("auth_domain"),
            initial_password=bool(result.get("initial_password", False)),
            connect_with_ap=bool(result.get("connectWithAp", False)),
            raw=result,
        )


@dataclass
class MotionConfig:
    """Result of ``Motion.GetConfig``.

    ``type`` is a pair of flags: ``all`` (any motion) and ``humanoid``
    (AI person detection). ``sensitivity`` is a 0-? integer scale.
    """

    enabled: bool = False
    detect_all: bool = False
    detect_human: bool = False
    sensitivity: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "MotionConfig":
        result = _as_dict(result)
        motion_type = _as_dict(result.get("type"))
        return cls(
            enabled=bool(result.get("motion_enable", False)),
            detect_all=bool(motion_type.get("all", False)),
            detect_human=bool(motion_type.get("humanoid", False)),
            sensitivity=int(result.get("sensitivity", 0) or 0),
            raw=result,
        )

    def to_params(self) -> Dict[str, Any]:
        """Serialise back into the ``params`` shape accepted by the device."""
        return {
            "motion_enable": self.enabled,
            "type": {"all": self.detect_all, "humanoid": self.detect_human},
            "sensitivity": self.sensitivity,
        }


@dataclass
class NightVisionConfig:
    """Result of ``NightVision.GetConfig``."""

    mode: Any = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "NightVisionConfig":
        result = _as_dict(result)
        return cls(mode=result.get("mode", result.get("night_vision")), raw=result)


@dataclass
class ScreenConfig:
    """Result of ``Screen.GetConfig`` (watermark / flip / OSD)."""

    watermark_display: bool = False
    screen_flip: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "ScreenConfig":
        result = _as_dict(result)
        return cls(
            watermark_display=bool(result.get("watermarkDisplay", False)),
            screen_flip=bool(result.get("screenFlip", False)),
            raw=result,
        )


@dataclass
class OnvifConfig:
    """Result of ``Onvif.GetConfig``."""

    enabled: bool = False
    user: str = ""
    ip: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(cls, result: Dict[str, Any]) -> "OnvifConfig":
        result = _as_dict(result)
        return cls(
            enabled=bool(result.get("enable", False)),
            user=str(result.get("user", "")),
            ip=str(result.get("ip", "")),
            raw=result,
        )


@dataclass
class CameraEvent:
    """A single entry from a ``NotifyEvent`` notification.

    ``component`` is the subsystem that raised the event (e.g. ``"Motion"``)
    and ``event`` is the verb (e.g. ``"motion_detected"``).
    """

    component: str = ""
    event: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_notification(cls, payload: Dict[str, Any]) -> List["CameraEvent"]:
        events: List["CameraEvent"] = []
        for entry in _as_dict(payload).get("events", []) or []:
            entry = _as_dict(entry)
            events.append(
                cls(
                    component=str(entry.get("component", "")),
                    event=str(entry.get("event", "")),
                    raw=entry,
                )
            )
        return events


@dataclass
class StatusUpdate:
    """A ``NotifyStatus`` notification.

    The device sends ``{"<key>": <value>, ..., "ts": <epoch>}``; this model
    surfaces ``key``/``value`` while keeping the whole payload.
    """

    key: str = ""
    value: Any = None
    timestamp: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_notification(cls, payload: Dict[str, Any]) -> Optional["StatusUpdate"]:
        payload = _as_dict(payload)
        item = next(((k, v) for k, v in payload.items() if k != "ts"), None)
        if item is None:
            return None
        key, value = item
        ts = payload.get("ts")
        return cls(
            key=str(key),
            value=value,
            timestamp=int(ts) if isinstance(ts, (int, float)) else None,
            raw=payload,
        )


@dataclass
class DiscoveredCamera:
    """A camera located on the local network by :mod:`sonoff_cam.discovery`."""

    ip: str
    rtsp_port: int = 554
    http_port: int = 80
    rtsp_server: Optional[str] = None
    model: Optional[str] = None
    name: Optional[str] = None
    firmware: Optional[str] = None
    mac: Optional[str] = None
    device_id: Optional[str] = None
    rpc_available: bool = False
    onvif_available: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        label = self.name or self.model or "SONOFF camera"
        return f"{label} @ {self.ip} (fw={self.firmware or '?'})"
