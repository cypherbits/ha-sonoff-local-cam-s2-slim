"""Minimal RTSP client for the camera's video service.

The stock firmware exposes exactly one stream::

    rtsp://admin:<password>@<ip>:554/av_stream/ch0

Authentication is HTTP *Digest* (MD5) with ``realm="SONOFF_rtspserver"``. This
module can build the URL, probe the server banner/Capabilities without decoding
video, and return the SDP so callers can discover the codecs. It deliberately
does not implement RTP depacketisation - use a media library (ffmpeg, VLC,
go2rtc, PyAV) for the actual decoding.
"""

from __future__ import annotations

import hashlib
import re
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

DEFAULT_RTSP_PORT = 554
DEFAULT_STREAM_PATH = "/av_stream/ch0"


@dataclass
class RtspProbe:
    """Result of an unauthenticated :func:`probe`."""

    server: Optional[str] = None
    public_methods: List[str] = field(default_factory=list)
    requires_auth: bool = False
    realm: Optional[str] = None
    scheme: Optional[str] = None


@dataclass
class RtspDescription:
    """Result of an authenticated ``DESCRIBE``."""

    status: int
    sdp: str
    media_types: List[str] = field(default_factory=list)
    media_controls: List[str] = field(default_factory=list)


def build_rtsp_url(
    host: str,
    path: str = DEFAULT_STREAM_PATH,
    *,
    user: Optional[str] = None,
    password: Optional[str] = None,
    port: int = DEFAULT_RTSP_PORT,
) -> str:
    """Return an RTSP URL, embedding credentials when supplied."""
    if not path.startswith("/"):
        path = "/" + path
    auth = ""
    if user:
        auth = f"{user}:{password}@" if password is not None else f"{user}@"
    return f"rtsp://{auth}{host}:{port}{path}"


_HEADER_RE = re.compile(r"^([A-Za-z0-9\-]+)\s*:\s*(.*)$")


def parse_headers(response: str) -> Dict[str, str]:
    """Parse RTSP response headers into a case-insensitive dict (canonicalised)."""
    headers: Dict[str, str] = {}
    for line in response.splitlines()[1:]:
        line = line.strip()
        if not line:
            break
        match = _HEADER_RE.match(line)
        if match:
            headers[match.group(1).lower()] = match.group(2).strip()
    return headers


def parse_www_authenticate(header: str) -> Dict[str, str]:
    """Parse a ``WWW-Authenticate`` Digest header into a dict of parameters."""
    if not header:
        return {}
    value = header.strip()
    scheme = value.split(" ", 1)[0]
    params: Dict[str, str] = {"scheme": scheme}
    for key, whole, quoted, bare in re.findall(r"(\w+)=(\"([^\"]*)\"|([^,]+))", value):
        params[key] = (quoted or bare).strip().strip('"')
    return params


def digest_authorization(
    method: str,
    uri: str,
    user: str,
    password: str,
    challenge: Dict[str, str],
) -> str:
    """Build a Digest ``Authorization`` header value (MD5, RFC 2617)."""
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")

    def md5(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    ha1 = md5(f"{user}:{realm}:{password}")
    ha2 = md5(f"{method}:{uri}")
    response = md5(f"{ha1}:{nonce}:{ha2}")
    parts = [
        f'username="{user}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
    ]
    if challenge.get("qop"):
        parts.append("qop=auth")
        parts.append("nc=00000001")
        parts.append('cnonce="sonoffcam"')
    return "Digest " + ", ".join(parts)


class RtspClient:
    """Tiny blocking RTSP client (OPTIONS/DESCRIBE) with optional digest auth."""

    def __init__(self, host: str, *, port: int = DEFAULT_RTSP_PORT, timeout: float = 6.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._cseq = 0

    def __enter__(self) -> "RtspClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _request(
        self,
        method: str,
        url: str,
        extra_headers: Optional[Dict[str, str]] = None,
        *,
        read_bytes: int = 65536,
    ) -> Tuple[str, str]:
        if self._sock is None:
            self.connect()
        assert self._sock is not None
        self._cseq += 1
        lines = [f"{method} {url} RTSP/1.0", f"CSeq: {self._cseq}", "User-Agent: sonoff-cam/0.1"]
        for key, value in (extra_headers or {}).items():
            lines.append(f"{key}: {value}")
        request = "\r\n".join(lines) + "\r\n\r\n"
        self._sock.sendall(request.encode("latin1"))
        try:
            raw = self._sock.recv(read_bytes)
        except socket.timeout:
            raw = b""
        text = raw.decode("latin1", "replace")
        head, _, body = text.partition("\r\n\r\n")
        return head, body

    def options(self, url: Optional[str] = None) -> Tuple[int, Dict[str, str]]:
        url = url or f"rtsp://{self.host}:{self.port}/"
        head, _ = self._request("OPTIONS", url)
        status = _status_code(head)
        return status, parse_headers(head)

    def describe(
        self,
        path: str = DEFAULT_STREAM_PATH,
        *,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> RtspDescription:
        """Run ``DESCRIBE`` and return the SDP, retrying once with digest auth."""
        url = f"rtsp://{self.host}:{self.port}{path}"
        head, body = self._request("DESCRIBE", url, {"Accept": "application/sdp"})
        status = _status_code(head)
        headers = parse_headers(head)

        if status == 401 and user is not None and password is not None:
            challenge = parse_www_authenticate(headers.get("www-authenticate", ""))
            authorization = digest_authorization("DESCRIBE", url, user, password, challenge)
            head, body = self._request(
                "DESCRIBE", url, {"Accept": "application/sdp", "Authorization": authorization}
            )
            status = _status_code(head)

        return RtspDescription(
            status=status,
            sdp=body,
            media_types=re.findall(r"m=([\w/]+)", body),
            media_controls=re.findall(r"a=control:(\S+)", body),
        )


def _status_code(head: str) -> int:
    match = re.search(r"RTSP/\d\.\d\s+(\d{3})", head)
    return int(match.group(1)) if match else 0


def probe(host: str, *, port: int = DEFAULT_RTSP_PORT, timeout: float = 6.0) -> RtspProbe:
    """Fingerprint the RTSP service without credentials."""
    result = RtspProbe()
    with RtspClient(host, port=port, timeout=timeout) as client:
        status, headers = client.options()
        result.server = headers.get("server")
        public = headers.get("public")
        if public:
            result.public_methods = [item.strip() for item in public.split(",") if item.strip()]
        desc_head, _ = client._request("DESCRIBE", f"rtsp://{host}:{port}{DEFAULT_STREAM_PATH}")
        if _status_code(desc_head) == 401:
            result.requires_auth = True
            challenge = parse_www_authenticate(parse_headers(desc_head).get("www-authenticate", ""))
            result.realm = challenge.get("realm")
            result.scheme = challenge.get("scheme")
        elif _status_code(desc_head) == 200:
            result.requires_auth = False
    return result


def is_sonoff_rtsp(server: Optional[str]) -> bool:
    """Heuristic used by discovery: the vendor banner is ``SONOFF_rtspserver``."""
    return bool(server) and "sonoff" in server.lower()
