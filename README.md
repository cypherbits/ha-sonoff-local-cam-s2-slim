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
| `media_player` | **Speaker** — play audio/TTS through the camera's speaker (local WebRTC) |
| `binary_sensor` | Motion, Person detection — real-time via ONVIF |
| `event` | Motion, Person — one event per detection (use in automations) |
| `switch` | Motion detection, Person detection, Detect-all-motion, Motion schedule, Alarm armed, Alarm on motion, Alarm on person, Alarm schedule, Status LED, Watermark, Flip image, ONVIF, Automatic updates, WebSocket client |
| `select` | Night vision mode (auto/on/off), Time zone, Stream resolution, Alarm sound |
| `number` | Motion sensitivity, Speaker volume, Microphone volume, Alarm duration |
| `sensor` | Wi-Fi signal, Wi-Fi network, IP address, Wi-Fi status, AP clients, Uptime, Free/Total/Lowest RAM, Firmware size, Flash size, Active/Max viewers, Camera time, Last time sync |
| `time` | Motion/alarm schedule start & end, Firmware update window |
| `text` | NTP server 1/2, Local domain |
| `button` | Reboot, Scan Wi-Fi, Sync time, Check for firmware update, Factory reset |
| `update` | Firmware (reports and can install the vendor OTA) |

State is refreshed by a coordinator (default every 60 s, configurable). Motion
and person detection are **pushed** from the camera's ONVIF PullPoint service,
so they react immediately. Many entities are `diagnostic`/`config` and are
**disabled by default** (schedules, NTP, time zone, sound, factory reset, …);
enable them from the entity's settings when you need them.

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

The add-integration dialog offers two paths:

* **Add manually** — enter the host, port and password yourself.
* **Scan the network** — the integration sweeps your LAN for SONOFF cameras
  (RTSP banner `SONOFF_rtspserver`) and lists what it finds; pick one and enter
  its password if prompted.

If the camera is found automatically over **DHCP** (MAC prefix `2CCC7A`) or
**mDNS** (`_rtsp._tcp`), Home Assistant also offers a **discovered** card;
confirm it and enter the password.

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
* **Motion schedule** — arms the detector only inside a time window.
  *Disabled by default.*
* **Alarm armed** — enables the on-board siren (`enableAlarm`).
* **Alarm on motion** / **Alarm on person** — which detectors sound the siren.
* **Alarm schedule** — arms the siren only inside a time window.
  *Disabled by default.*
* **Status LED** — the camera's indicator LED.
* **On-screen watermark** — timestamp/OSD overlay.
* **Flip image** — 180° rotation. *Disabled by default.*
* **ONVIF** — turns the camera's ONVIF service on/off.
* **Automatic firmware updates** — *Disabled by default.*
* **WebSocket client** — the camera's outbound WebSocket client config.
  *Disabled by default.*

### Selects

* **Night vision mode** — Auto / Always on / Always off (`infraredSetting`).
* **Time zone** — the camera's time zone. *Disabled by default.*
* **Stream resolution** — `1080P` or `360P`.
* **Alarm sound** — the siren sound (`arm1`…). *Disabled by default.*

### Numbers

* **Motion sensitivity** — 0–10.
* **Speaker volume** — 0–100 %.
* **Microphone volume** — 0–100 %.
* **Alarm duration** — siren blast length in seconds (1–60).

### Sensors

* **Wi-Fi signal** — RSSI in dBm.
* **Wi-Fi network** — connected SSID.
* **IP address** — current station IP.
* **Wi-Fi status** / **AP clients** — *Disabled by default.*
* **Uptime** — seconds since boot.
* **Free RAM** / **Total RAM** / **Lowest free RAM** — kilobytes.
* **Firmware size** / **Flash size** — kilobytes / megabytes.
* **Active viewers** / **Maximum viewers** — RTSP viewers.
* **Camera time** / **Last time sync** — device clock.

### Time

* **Motion schedule start / end**, **Alarm schedule start / end** — the daily
  window for each schedule. *Disabled by default.*
* **Update window start / end** — the camera's OTA maintenance window.
  *Disabled by default.*

### Text

* **NTP server 1 / 2** and **Local domain** — device networking settings.
  *Disabled by default.*

### Buttons

* **Reboot** — restarts the camera.
* **Scan Wi-Fi networks** — runs `WiFi.Scan` and fires a `sonoff_cam_local_wifi_scan`
  event with the results.
* **Sync time** — writes Home Assistant's clock to the camera.
* **Check for firmware update** — asks the camera to check for an update.
* **Factory reset** — wipes the camera. *Disabled by default; destructive.*

### Update

* **Firmware** — reports the installed version, the changelog URL and any OTA
  update. Pressing **Install** triggers the vendor OTA (the camera downloads
  and installs from SONOFF's servers, then reboots). *Disabled by default.*

### Speaker (`media_player`)

* **Speaker** — plays audio through the camera's built-in speaker. Use
  `media_player.play_media` (a URL or local file) or `tts.speak`. It is
  **one-way playback** (announcements, TTS, sounds), not a live intercom — Home
  Assistant does not capture a microphone for it.

The stock firmware exposes **no** RPC/RTSP/ONVIF way to send audio (verified:
`Alarm.*`/`Speaker.Play` answer `-103`, the RTSP server ignores the ONVIF
backchannel `Require` header and `ANNOUNCE`/`RECORD`). The eWeLink app's two-way
"Talk" uses the camera's **local WebRTC** endpoint (an Amazon Kinesis Video
Streams peer), which its web console only uses with a `recvonly` audio track.
The peer actually accepts a `sendrecv` **PCMA/8000** track, and that is what this
entity uses.

```yaml
# TTS example
action: tts.speak
data:
  entity_id: tts.home_assistant_cloud
  media_player_entity_id: media_player.cam_s2_speaker
  message: "Someone is at the front door"
```

> **Dependency note**: the WebRTC client uses
> [`aiortc`](https://github.com/aiortc/aiortc). HA pins `av==19`, while the last
> aiortc *release* caps `av<18`, so the manifest pins aiortc to a specific
> `main` commit (which allows `av<20`). This will be switched to a released
> version once one is available.

### Alarm / siren

`Alarm.GetConfig` exposes the camera's on-board siren. There is **no manual
trigger**: the siren sounds when *Alarm armed* is on, at least one of *Alarm on
motion* / *Alarm on person* is on, and the matching detector actually fires. The
sound lasts *Alarm duration* seconds. All alarm writes are read-modify-write, so
toggling one setting never clobbers the others.

---

## Automations

Motion and person detection are binary sensors, so use them directly:

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

There are also **device triggers** (*detected motion* / *detected a person*) and
`event` entities (`event.cam_s2_motion`, `event.cam_s2_person`), which fire once
per detection — better suited to "every occurrence" automations than a binary
sensor's on/off state.

```yaml
automation:
  - alias: Chime on every motion
    triggers:
      - trigger: device
        device_id: <camera-device-id>
        domain: sonoff_cam_local
        type: motion_detected
    actions:
      - action: media_player.play_media
        target:
          entity_id: media_player.kitchen
        data:
          media_content_id: /local/chime.mp3
          media_content_type: music
```

---

## Services

### `sonoff_cam_local.set_wifi`

Joins a new Wi-Fi network. **This drops the camera off its current network**; if
the credentials are wrong the camera becomes unreachable over Wi-Fi and must be
recovered in AP setup mode.

```yaml
action: sonoff_cam_local.set_wifi
data:
  device_id: <camera-device-id>
  ssid: MyHomeWiFi
  password: "secret"
```

When a Wi-Fi scan is started (button or `sonoff_cam_local_wifi_scan` event), the
results are delivered as a bus event:

```yaml
triggers:
  - trigger: event
    event_type: sonoff_cam_local_wifi_scan
```

---

## Diagnostics

**Settings → Devices & Services → SONOFF CAM-S2 → Download diagnostics**
produces a JSON dump of the camera's readable surface. Passwords, SSIDs and
inline RTSP/AP credentials are **redacted** before the file is produced.

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

Reference firmware: **2.2.2** (`SN-CAM-S2-01`).

---

## Notes & limitations

* **Firmware install** (the *Firmware* update entity's **Install** and the
  *Factory reset* button) is enabled but destructive — a wrong or interrupted
  flash can brick the camera. They are disabled by default; enable them only if
  you know what you are doing.
* The camera's siren has **no manual trigger** on stock firmware; it only sounds
  on a real detection while armed. See the *Alarm / siren* section.
* The camera hands back the **RTSP and AP passwords in cleartext** from
  `Onvif.GetConfig` / `WiFi.GetConfig`. They are never written to attributes and
  are redacted in diagnostics, but treat any raw dump as sensitive.
* `SetConfig` calls on this firmware are **read-modify-write**: omitting a field
  keeps its previous value. The integration always reads the full config first.
* The RPC push (`NotifyEvent`) stream is unreliable on stock firmware; motion and
  person events come from **ONVIF**.

---

## Legal & ethics

Use this only on equipment **you own** or are authorized to control. The
integration reproduces a reverse-engineered local protocol and is not affiliated
with, endorsed by, or supported by ITEAD/SONOFF. Provided **as is**, without
warranty.

## License

MIT — see [LICENSE](LICENSE).
