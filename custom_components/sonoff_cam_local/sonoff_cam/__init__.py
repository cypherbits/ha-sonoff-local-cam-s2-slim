"""Local-network control for the SONOFF CAM-S2 / CAM Slim Gen2 (stock firmware).

The camera is discovered by its RTSP banner (``SONOFF_rtspserver``) and controlled
through its local WebSocket JSON-RPC service on port 80 (``ws://<ip>/rpc``),
protected by a SHA-256 digest challenge. See ``docs/PROTOCOL.md`` for how the
protocol was reverse-engineered.

Quick start::

    import asyncio
    from sonoff_cam import SonoffCamera, discover

    for camera in discover():
        print(camera)

    async def main():
        async with SonoffCamera("192.168.1.100", password="secret") as cam:
            print(await cam.get_device_info())
            print(await cam.get_motion_config())

    asyncio.run(main())
"""

from __future__ import annotations

__version__ = "0.1.0"

from .auth import AuthChallenge, build_auth, compute_ha1, compute_ha2
from .client import SonoffCamera
from .discovery import discover, identify, scan
from .exceptions import (
    AuthenticationError,
    ConnectionFailed,
    NotSupported,
    ProtocolError,
    RpcError,
    SonoffCamError,
    Timeout,
)
from .methods import Method
from .models import (
    AlarmConfig,
    CameraEvent,
    DeviceInfo,
    DiscoveredCamera,
    EffectiveSchedule,
    MotionConfig,
    NightVisionConfig,
    OnvifConfig,
    ScreenConfig,
    StatusUpdate,
)
from .redact import PLACEHOLDER, redact, redact_text, redact_url_credentials
from .rtsp import RtspClient, build_rtsp_url, probe as rtsp_probe
from .rpc import RpcClient

__all__ = [
    "__version__",
    # client
    "SonoffCamera",
    "RpcClient",
    # auth
    "AuthChallenge",
    "build_auth",
    "compute_ha1",
    "compute_ha2",
    # discovery
    "discover",
    "identify",
    "scan",
    # models
    "AlarmConfig",
    "CameraEvent",
    "DeviceInfo",
    "DiscoveredCamera",
    "EffectiveSchedule",
    "MotionConfig",
    "NightVisionConfig",
    "OnvifConfig",
    "ScreenConfig",
    "StatusUpdate",
    # redaction
    "PLACEHOLDER",
    "redact",
    "redact_text",
    "redact_url_credentials",
    # rtsp
    "RtspClient",
    "build_rtsp_url",
    "rtsp_probe",
    # methods / errors
    "Method",
    "SonoffCamError",
    "ConnectionFailed",
    "Timeout",
    "RpcError",
    "AuthenticationError",
    "NotSupported",
    "ProtocolError",
]
