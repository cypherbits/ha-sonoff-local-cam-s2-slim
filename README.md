# SONOFF CAM-S2 (Local) — Home Assistant integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A **local-only** Home Assistant integration for the **SONOFF CAM-S2 / CAM Slim
Gen2** camera running **stock firmware**. It talks straight to the camera over
your LAN using the camera's own WebSocket JSON-RPC service (and ONVIF for
motion/people events). No SONOFF cloud, no eWeLink account and no internet
connection are required at runtime.

This integration bundles a copy of the reverse-engineered
[`sonoff-cam`](https://github.com/) client library, so the protocol details live
inside `custom_components/sonoff_cam_local/sonoff_cam/`.

---

## Features

| Platform | Entities |
|---|---|
| `camera` | Live RTSP stream (HLS/WebRTC through the `stream` integration) |
| `binary_sensor` | Motion, Person detection — real-time via ONVIF |
| `switch` | Motion detection, Person detection, Detect-all-motion, Status LED, Night vision, Watermark, Flip image, ONVIF, Automatic updates, WebSocket client |
| `number` | Motion sensitivity, Speaker volume, Microphone volume |
| `sensor` | Wi-Fi signal (dBm), Wi-Fi network, Uptime, Free RAM, Active viewers |
| `button` | Reboot |
| `update` | Firmware (informational) |

State is refreshed by a coordinator (default every 60 s, configurable). Motion
and person detection are **pushed** from the camera's ONVIF PullPoint service,
so they react immediately.

---

## Prerequisites

Before adding the integration:

1. **Set a local login password on the camera.** Open the camera's own web
   console (`http://<camera-ip>/`) and set the login password. This is the
   *local admin* password and is **not** the same as the RTSP password you may
   have set in the eWeLink app.
   * The very first password can only be set while the camera is in **AP setup
     mode**. Press and hold the camera button ~5 s until it beeps once, join the
     `SONOFF_S2_xxxx` hotspot, then set the password from the web console.
2. **Enable ONVIF** (for motion/person events). In the camera's web console,
   turn ONVIF on. The integration reads the RTSP/ONVIF credentials from the
   camera automatically.
3. Make sure Home Assistant can reach the camera's IP on ports **80** (RPC +
   ONVIF) and **554** (RTSP).

The RTSP credentials used for video and ONVIF are usually **different** from the
local admin password. You do **not** need to enter them: the integration reads
them from `Onvif.GetConfig` once you are logged in with the admin password.

---

## Installation

### HACS (recommended)

1. In Home Assistant go to **HACS → Integrations**.
2. Click the three-dot menu → **Custom repositories**.
3. Add `https://github.com/cypherbits/ha-sonoff-local-cam-s2-slim`
   with category **Integration**.
4. Find **SONOFF CAM-S2 (Local)** in HACS and click **Download**.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/sonoff_cam_local` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **SONOFF CAM-S2 (Local)**.
3. Fill in the form:

   | Field | Description |
   |---|---|
   | **Host** | The camera's IP address or hostname (e.g. `192.168.1.100`). |
   | **Port** | WebSocket JSON-RPC port. Leave at `80` unless you changed it. |
   | **Local admin password** | The password from step 1 above. Leave empty only if the camera has no password set. |

4. Home Assistant validates the connection and creates a device for the camera.

If the camera is found automatically over DHCP, Home Assistant offers a
**discovered** card; confirm it and enter the password.

### Options

Open the integration's **Configure** button to change:

* **Poll interval** — how often status is refreshed (15–600 s, default 60).
* **Enable ONVIF motion/person events** — turn the real-time event subscription
  on or off.

### Reauthentication

If you change the camera's password, Home Assistant raises a reauth prompt.
Enter the new password; no need to remove and re-add the camera.

---

## Entities

Names are shown as they appear after the device name, e.g.
`sensor.cam_s2_wifi_signal`.

### Camera

The single RTSP stream (`/av_stream/ch0`) with authentication. Use the
**Stream** dashboard card for live video. Still images are taken from the
stream (there is no separate snapshot endpoint on this firmware).

### Switches

* **Motion detection** — master switch (`motion_enable`).
* **Person detection** — AI humanoid detector (`type.humanoid`).
* **Detect all motion** — generic motion (`type.all`). *Disabled by default.*
* **Status LED** — the camera's indicator LED.
* **Night vision** — infrared.
* **On-screen watermark** — timestamp/OSD overlay.
* **Flip image** — 180° rotation. *Disabled by default.*
* **ONVIF** — turns the camera's ONVIF service on/off.
* **Automatic firmware updates** — *Disabled by default.*
* **WebSocket client** — the camera's outbound WebSocket client config.
  *Disabled by default.*

### Numbers

* **Motion sensitivity** — 0–10.
* **Speaker volume** — 0–100 %.
* **Microphone volume** — 0–100 %.

### Sensors

* **Wi-Fi signal** — RSSI in dBm.
* **Wi-Fi network** — connected SSID.
* **Uptime** — seconds since boot.
* **Free RAM** — kilobytes.
* **Active viewers** — current RTSP viewers.

### Button

* **Reboot** — restarts the camera.

### Update

* **Firmware** — reports the installed version and any OTA update advertised by
  the camera. *Informational only and disabled by default; installing an update
  from Home Assistant has not been verified on stock firmware.*

---

## Automations

Motion and person detection are proper binary sensors, so use them directly:

```yaml
automation:
  - alias: Notify on person at the front door
    triggers:
      - trigger: state
        entity_id: binary_sensor.cam_s2_person_detection
        to: "on"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          message: "Person detected at the front door"
```

---

## Troubleshooting

**"Invalid password" when adding the integration.**
You entered the RTSP password. Use the camera's **local admin** password
(the one for `http://<camera-ip>/`), which is usually different.

**"Failed to connect".**
Check the host/IP, that the camera is powered on, and that Home Assistant can
reach port 80. Discovery relies on the WebSocket endpoint at `/rpc`.

**Motion/person sensors never change.**
The camera's RPC push notifications are unreliable on stock firmware — this
integration deliberately uses ONVIF for events. Make sure **ONVIF is enabled**
on the camera (the `ONVIF` switch) and that the option
**Enable ONVIF motion/person events** is on. The first subscription can take a
few seconds.

**No video.**
The `stream` integration must be able to open the RTSP URL. Confirm the RTSP
credentials are correct (the integration reads them automatically; check the
**ONVIF** switch is enabled). The camera exposes only one stream.

**Enable debug logging.**

```yaml
logger:
  logs:
    custom_components.sonoff_cam_local: debug
```

---

## How it works

The camera exposes a WebSocket JSON-RPC service at `ws://<ip>/rpc` protected by
a SHA-256 digest challenge, plus RTSP on port 554 and an ONVIF server on port 80.
Home Assistant polls the JSON-RPC `Get*` methods for status and calls `Set*`
methods for control, while ONVIF PullPoint provides the motion/person events.
The bundled `sonoff_cam` package implements the digest handshake, the RPC
client, the typed models and a minimal RTSP/ONVIF helper.

---

## Legal & ethics

Use this only on equipment **you own** or are authorized to control. The
integration reproduces a reverse-engineered local protocol and is not affiliated
with, endorsed by, or supported by ITEAD/SONOFF. Provided **as is**, without
warranty.

## License

MIT — see [LICENSE](LICENSE).
