# Local test environment (Docker)

Runs Home Assistant in Docker with this integration mounted from the repository,
so you can test it before publishing to HACS.

## Requirements

- Docker Desktop running.
- The camera and the PC on the same LAN.

## Start

```bash
cd dev
docker compose up -d
docker compose logs -f homeassistant
```

Wait until the log shows Home Assistant has started, then open
<http://localhost:8123> and complete the onboarding (create your account).

## Add the integration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **SONOFF CAM-S2 (Local)**.
3. Choose **Add manually** and enter the camera's **IP**, port **80** and the
   camera's **local admin password** (the one for the camera's own web console,
   not the RTSP one). You can also choose **Scan the network** to find it.
4. Optional: open **Configure** to change the poll interval or toggle ONVIF
   motion/person events.

## Notes

- The integration's Python dependency (`websockets`) is installed into the
  container automatically on first load; give it a few seconds.
- Discovery over Docker's default bridge network is limited, so add the camera
  by IP rather than relying on auto-discovery.
- The Home Assistant configuration (database, `.storage`, etc.) is written to
  `dev/config/`, which is git-ignored.
- The container reaches the LAN through Docker's NAT, so the camera must be
  reachable from the host.

## Stop / clean up

```bash
docker compose down          # stop
docker compose down -v       # stop and remove the container
rm -rf config                # delete the test Home Assistant config
```
