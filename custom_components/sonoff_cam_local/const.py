"""Constants for the SONOFF CAM-S2 (Local) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sonoff_cam_local"
MANUFACTURER: Final = "SONOFF"

# --- Configuration keys -----------------------------------------------------
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_PASSWORD: Final = "password"
CONF_RTSP_USERNAME: Final = "rtsp_username"
CONF_RTSP_PASSWORD: Final = "rtsp_password"
CONF_ENABLE_ONVIF: Final = "enable_onvif_motion"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# --- Defaults ---------------------------------------------------------------
DEFAULT_PORT: Final = 80
DEFAULT_RPC_USERNAME: Final = "admin"
DEFAULT_RTSP_USERNAME: Final = "sonoff"
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 600

# --- RTSP -------------------------------------------------------------------
RTSP_PORT: Final = 554
RTSP_STREAM_PATH: Final = "/av_stream/ch0"

# --- ONVIF events -----------------------------------------------------------
ONVIF_EVENTS_PATH: Final = "/onvif/events_service"
ONVIF_PORT_TYPE: Final = "http://www.onvif.org/ver10/events/wsdl/EventPortType"
ONVIF_SUBSCRIPTION_LIFETIME: Final = "PT900S"
ONVIF_PULL_TIMEOUT: Final = "PT5S"
ONVIF_PULL_MESSAGE_LIMIT: Final = 32
ONVIF_RECONNECT_DELAY: Final = 15
