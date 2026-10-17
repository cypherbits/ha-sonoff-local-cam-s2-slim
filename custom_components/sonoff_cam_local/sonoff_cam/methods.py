"""RPC method names exposed by the SONOFF CAM-S2 local service.

Most were extracted verbatim from the ``sonoff-camera-web`` bundle served on
port 80 of the device (firmware 2.2.2). See ``docs/PROTOCOL.md`` for the full
narrative.

.. warning::
   The bundle is **not** an exhaustive list of the firmware's methods. The whole
   ``Alarm`` component is absent from it -- the string "Alarm" does not appear
   anywhere in the bundle -- yet ``Alarm.GetConfig`` answers with real data. New
   methods are found by probing candidate ``<Component>.GetConfig`` /
   ``<Component>.GetStatus`` names against the device, not by reading the bundle.
"""

from __future__ import annotations


class Method:
    """Canonical RPC method strings."""

    # --- Live stream -----------------------------------------------------
    LIVE_STREAM_GET_STATUS = "LiveStream.GetStatus"
    LIVE_STREAM_SET_CONFIG = "LiveStream.SetConfig"

    # --- Audio -----------------------------------------------------------
    MICROPHONE_GET_CONFIG = "Microphone.GetConfig"
    MICROPHONE_SET_CONFIG = "Microphone.SetConfig"
    SPEAKER_GET_CONFIG = "Speaker.GetConfig"
    SPEAKER_SET_CONFIG = "Speaker.SetConfig"

    # --- Detection / image ----------------------------------------------
    MOTION_GET_CONFIG = "Motion.GetConfig"
    MOTION_SET_CONFIG = "Motion.SetConfig"

    # --- Alarm (not in the web bundle; found by probing the device) ------
    ALARM_GET_CONFIG = "Alarm.GetConfig"
    ALARM_SET_CONFIG = "Alarm.SetConfig"
    NIGHT_VISION_GET_CONFIG = "NightVision.GetConfig"
    NIGHT_VISION_SET_CONFIG = "NightVision.SetConfig"
    SCREEN_GET_CONFIG = "Screen.GetConfig"
    SCREEN_SET_CONFIG = "Screen.SetConfig"

    # --- Connectivity ----------------------------------------------------
    ONVIF_GET_CONFIG = "Onvif.GetConfig"
    ONVIF_SET_CONFIG = "Onvif.SetConfig"
    WEBRTC_SET_CONFIG = "Webrtc.SetConfig"

    # --- Device / identity ----------------------------------------------
    SONOFF_GET_DEVICE_INFO = "Sonoff.GetDeviceInfo"
    SONOFF_GET_CONFIG = "Sonoff.GetConfig"
    SONOFF_SET_CONFIG = "Sonoff.SetConfig"
    SONOFF_SET_AUTH = "Sonoff.SetAuth"
    SONOFF_RESET_AUTH = "Sonoff.ReSetAuth"
    SONOFF_FORGET_AUTH = "Sonoff.ForgetAuth"

    # --- Status indicator -------------------------------------------------
    SLED_GET_CONFIG = "Sled.GetConfig"
    SLED_SET_CONFIG = "Sled.SetConfig"

    # --- System -----------------------------------------------------------
    SYSTEM_GET_STATUS = "System.GetStatus"
    SYSTEM_GET_CONFIG = "System.GetConfig"
    SYSTEM_SET_CONFIG = "System.SetConfig"
    SYSTEM_CONTROL = "System.Control"
    SYSTEM_SET_TIME = "System.SetTime"
    SYSTEM_GET_TIMEZONE = "System.GetTimeZone"
    SYSTEM_SET_TIMEZONE = "System.SetTimeZone"
    SYSTEM_GET_CERTS_INFO = "System.GetCertsInfo"
    SYSTEM_PUT_USER_CA = "System.PutUserCA"
    SYSTEM_PUT_TLS_CLIENT_CERT = "System.PutTLSClientCert"
    SYSTEM_PUT_TLS_CLIENT_KEY = "System.PutTLSClientKey"

    # --- WebSocket (client config) ---------------------------------------
    WEBSOCKET_GET_CONFIG = "WebSocket.GetConfig"
    WEBSOCKET_SET_CONFIG = "WebSocket.SetConfig"
    WEBSOCKET_GET_STATUS = "WebSocket.GetStatus"
    WEBSOCKET_GET_CERTS_INFO = "WebSocket.GetCertsInfo"
    WEBSOCKET_PUT_USER_CA = "WebSocket.PutUserCA"
    WEBSOCKET_PUT_TLS_CLIENT_CERT = "WebSocket.PutTLSClientCert"
    WEBSOCKET_PUT_TLS_CLIENT_KEY = "WebSocket.PutTLSClientKey"

    # --- Wi-Fi ------------------------------------------------------------
    WIFI_GET_CONFIG = "WiFi.GetConfig"
    WIFI_SET_CONFIG = "WiFi.SetConfig"
    WIFI_GET_STATUS = "WiFi.GetStatus"
    WIFI_SCAN = "WiFi.Scan"

    # --- OTA / upgrade ----------------------------------------------------
    OTA_GET_CONFIG = "Ota.GetConfig"
    OTA_SET_CONFIG = "Ota.SetConfig"
    OTA_GET_STATUS = "Ota.GetStatus"
    UPGRADE_START = "Upgrade.Start"
    UPGRADE_GET_STATUS = "Upgrade.GetStatus"
    UPGRADE_UPLOAD = "Upgrade.Upload"
    UPGRADE_FINISH = "Upgrade.Finish"

    # --- Server -> client notifications ----------------------------------
    NOTIFY_EVENT = "NotifyEvent"
    NOTIFY_STATUS = "NotifyStatus"


#: Methods that are safe to call without authentication. ``Sonoff.GetDeviceInfo``
#: is not in the official PRE_AUTH list but the device answers it anyway.
PRE_AUTH_METHODS = frozenset({Method.SONOFF_GET_DEVICE_INFO})

#: Methods that must never carry an ``auth`` field (used to bootstrap/reset).
NO_AUTH_METHODS = frozenset({Method.SONOFF_RESET_AUTH})

#: Notification ``component`` names carried inside ``NotifyEvent``/``NotifyStatus``.
#: Every one of these was observed in the bundle's notification router. ``Alarm``
#: is deliberately NOT listed: it is a valid RPC component, but nothing has shown
#: it emitting a notification, and adding an unverified entry here would make
#: :meth:`SonoffCamera._decode_notification` claim to handle something it does not.
EVENT_COMPONENTS = ("Motion", "NightVision", "Screen", "Sled", "Onvif", "Sonoff", "System", "Ota")
