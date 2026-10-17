"""Discover SONOFF cameras on the local network.

Discovery is deliberately passive and lightweight:

1. Sweep a /24 (or the subnets given) for hosts with TCP 554 and/or 80 open.
2. Fingerprint each hit with an RTSP ``OPTIONS`` request - the stock firmware
   answers with ``Server: SONOFF_rtspserver (build date)``.
3. Optionally confirm the JSON-RPC surface by attempting a WebSocket upgrade on
   ``/rpc`` and read ``Sonoff.GetDeviceInfo`` for the model/name/firmware.

Only the standard library is used, so discovery works without extra deps.
"""

from __future__ import annotations

import base64
import concurrent.futures
import ipaddress
import json
import os
import socket
from typing import Dict, Iterable, List, Optional, Sequence

from .models import DiscoveredCamera
from .rtsp import is_sonoff_rtsp, parse_headers, _status_code  # noqa: F401

DEFAULT_PORTS = (554, 80)


def local_ip() -> Optional[str]:
    """Return the primary local IPv4 address, or ``None`` when offline."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def default_subnet() -> Optional[str]:
    """Return the ``/24`` network derived from :func:`local_ip`."""
    ip = local_ip()
    if not ip:
        return None
    network = ipaddress.ip_network(f"{ip}/24", strict=False)
    return str(network)


def _tcp_open(ip: str, port: int, timeout: float) -> bool:
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def scan(
    subnet: Optional[str] = None,
    *,
    ports: Sequence[int] = DEFAULT_PORTS,
    timeout: float = 0.35,
    workers: int = 128,
) -> Dict[str, List[int]]:
    """Return ``{ip: [open_ports]}`` for every reachable host in ``subnet``."""
    subnet = subnet or default_subnet()
    if not subnet:
        return {}
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(host) for host in network.hosts()]

    def probe(ip: str) -> tuple:
        open_ports = [port for port in ports if _tcp_open(ip, port, timeout)]
        return ip, open_ports

    results: Dict[str, List[int]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for ip, open_ports in pool.map(probe, hosts):
            if open_ports:
                results[ip] = open_ports
    return results


def _http_headers(host: str, port: int = 80, timeout: float = 3.0, path: str = "/") -> Optional[Dict[str, str]]:
    """Fetch response headers for a plain HTTP GET (used to fingerprint :80)."""
    request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(request.encode("latin1"))
            raw = sock.recv(4096).decode("latin1", "replace")
    except OSError:
        return None
    head = raw.split("\r\n\r\n", 1)[0]
    return parse_headers(head)


def ws_upgrade_available(host: str, *, port: int = 80, path: str = "/rpc", timeout: float = 3.0) -> bool:
    """Return ``True`` when ``/rpc`` answers a WebSocket upgrade with ``101``."""
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(request.encode("latin1"))
            first = sock.recv(256).decode("latin1", "replace")
    except OSError:
        return False
    return "101" in first.split("\r\n", 1)[0]


def identify(ip: str, *, rtsp_port: int = 554, http_port: int = 80, timeout: float = 6.0) -> DiscoveredCamera:
    """Fingerprint a single host without authenticating."""
    from .rtsp import RtspClient

    camera = DiscoveredCamera(ip=ip, rtsp_port=rtsp_port, http_port=http_port)

    try:
        with RtspClient(ip, port=rtsp_port, timeout=timeout) as client:
            status, headers = client.options()
            camera.rtsp_server = headers.get("server")
            desc_head, _ = client._request(  # noqa: SLF001 - same package
                "DESCRIBE", f"rtsp://{ip}:{rtsp_port}/av_stream/ch0"
            )
            if _status_code(desc_head) == 401:
                camera.raw["rtsp_requires_auth"] = True
    except OSError:
        pass

    if _tcp_open(ip, http_port, timeout):
        headers = _http_headers(ip, http_port, timeout)
        if headers:
            camera.raw["http_server"] = headers.get("server")
        camera.rpc_available = ws_upgrade_available(ip, port=http_port, timeout=timeout)

    info = get_device_info_unauthenticated(ip, http_port) if camera.rpc_available else None
    if info and is_sonoff_device_info(info):
        camera.name = info.get("name")
        camera.model = info.get("model")
        camera.firmware = info.get("ver")
        camera.mac = info.get("mac")
        camera.device_id = info.get("id")
        camera.raw["device_info"] = info

    return camera


def is_sonoff_device_info(info: Optional[dict]) -> bool:
    """True when a ``Sonoff.GetDeviceInfo`` payload really is a SONOFF camera."""
    if not isinstance(info, dict):
        return False
    model = str(info.get("model", ""))
    device_id = str(info.get("id", ""))
    return model.startswith("SN-") or device_id.startswith("sonoffcam")


def rpc_get_device_info(ip: str) -> Optional[dict]:
    """Placeholder kept for API symmetry; see :func:`get_device_info_unauthenticated`."""
    return get_device_info_unauthenticated(ip)


def get_device_info_unauthenticated(ip: str, port: int = 80, timeout: float = 6.0) -> Optional[dict]:
    """Open ``/rpc`` and read ``Sonoff.GetDeviceInfo`` (allowed pre-auth)."""
    try:
        from .rpc import RpcClient
    except ImportError:  # pragma: no cover
        return None

    import asyncio

    async def _run() -> Optional[dict]:
        client = RpcClient(ip, password=None, port=port, timeout=timeout)
        await client.connect()
        try:
            result = await client.call("Sonoff.GetDeviceInfo")
            return result
        finally:
            await client.close()

    try:
        return asyncio.run(_run())
    except Exception:  # noqa: BLE001 - discovery must never raise
        return None


def discover(
    subnet: Optional[str] = None,
    *,
    ports: Sequence[int] = DEFAULT_PORTS,
    timeout: float = 0.35,
    deep: bool = True,
) -> List[DiscoveredCamera]:
    """Scan ``subnet`` and return identified cameras (vendor banner + RPC)."""
    found: List[DiscoveredCamera] = []
    for ip, open_ports in scan(subnet, ports=ports, timeout=timeout).items():
        if 554 not in open_ports and 80 not in open_ports:
            continue
        camera = identify(ip) if deep else DiscoveredCamera(ip=ip)
        if not deep:
            camera.raw["open_ports"] = open_ports
            found.append(camera)
            continue
        if is_sonoff_rtsp(camera.rtsp_server) or "device_info" in camera.raw:
            found.append(camera)
    return found
