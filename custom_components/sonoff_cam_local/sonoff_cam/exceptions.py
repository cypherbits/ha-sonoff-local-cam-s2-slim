"""Exception hierarchy for :mod:`sonoff_cam`.

All library errors derive from :class:`SonoffCamError` so callers can catch a
single base type.
"""

from __future__ import annotations

from typing import Any, Optional


class SonoffCamError(Exception):
    """Base class for every error raised by this library."""


class ConnectionFailed(SonoffCamError):
    """The TCP/WebSocket connection to the camera could not be established."""


class Timeout(SonoffCamError):
    """An RPC request did not receive a reply within the configured timeout."""


class RpcError(SonoffCamError):
    """The camera replied with a JSON-RPC ``error`` object.

    Attributes
    ----------
    code:
        Numeric error code reported by the device (e.g. ``401`` for an
        authentication challenge).
    message:
        Raw ``message`` field returned by the device.
    data:
        Optional structured payload. For authentication challenges this is a
        dict with ``nonce``/``realm``/``algorithm``.
    method:
        The RPC method that produced the error, when known.
    """

    def __init__(
        self,
        code: int,
        message: str = "",
        *,
        data: Optional[dict] = None,
        method: Optional[str] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.data = data
        self.method = method
        super().__init__(f"[{code}] {message}" + (f" (method={method})" if method else ""))


class AuthenticationError(RpcError):
    """Authentication failed (wrong password, or a malformed challenge)."""


class NotSupported(SonoffCamError):
    """The device does not expose the requested capability."""


class ProtocolError(SonoffCamError):
    """A reply could not be parsed or did not follow the expected protocol."""


class AlreadyConnected(SonoffCamError):
    """A connection was requested while one is already active."""


def error_from_payload(payload: Any, method: Optional[str] = None) -> RpcError:
    """Build an :class:`RpcError` from a JSON-RPC ``error`` object.

    The device sometimes nests a JSON string inside ``message`` (used for the
    digest challenge). That string is parsed into ``data`` when possible.
    """
    import json

    if not isinstance(payload, dict):
        return RpcError(-1, str(payload), method=method)

    code = int(payload.get("code", -1))
    message = str(payload.get("message", ""))
    data = payload.get("data")

    if isinstance(message, str) and message.strip().startswith("{"):
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            data = parsed

    if isinstance(data, dict) and "nonce" in data:
        if code == 401:
            # A 401 is expected during the handshake; only a *failure* after we
            # answered the challenge is a real AuthenticationError.
            return AuthenticationError(code, message, data=data, method=method)

    return RpcError(code, message, data=data, method=method)
