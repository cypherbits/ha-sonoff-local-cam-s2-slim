"""Async JSON-RPC client for the SONOFF CAM-S2 local WebSocket service.

Frame format (JSON over ``ws://<host>/rpc``)::

    request  : {"jsonrpc":"2.0","id":<int>,"method":"Motion.GetConfig",
                "params":{...},"src":"web"[, "auth":{...}]}
    response : {"id":<int>,"jsonrpc":"2.0","src":<device-id>,"dst":"web",
                "result":{...}}            # success
               {"id":<int>,"error":{"code":<int>,"message":"..."}}
    notif.   : {"jsonrpc":"2.0","method":"NotifyEvent",
                "params":{"events":[{"component":"Motion","event":"..."}]}}
               {"jsonrpc":"2.0","method":"NotifyStatus",
                "params":{"<key>":<value>,"ts":<epoch>}}

The client transparently answers the digest challenge (see :mod:`sonoff_cam.auth`)
and never blocks waiting for notifications: one background task reads the socket
and routes frames to pending requests or to event listeners.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:  # websockets >= 12 (modern asyncio client)
    from websockets.asyncio.client import connect as _ws_connect
except ImportError:  # pragma: no cover - older websockets
    from websockets.client import connect as _ws_connect  # type: ignore

from websockets.exceptions import ConnectionClosed

from .auth import AuthChallenge, build_auth
from .exceptions import (
    AuthenticationError,
    ConnectionFailed,
    ProtocolError,
    RpcError,
    Timeout,
    error_from_payload,
)
from .methods import Method, NO_AUTH_METHODS

NotificationHandler = Callable[[Dict[str, Any]], Any]

#: Methods that are answered without authentication and used to bootstrap.
_BOOTSTRAP_METHOD = Method.SONOFF_GET_DEVICE_INFO


class RpcClient:
    """A single WebSocket JSON-RPC connection to the camera.

    Parameters
    ----------
    host:
        Camera IP address or hostname.
    password:
        Local admin password (the one set from the eWeLink app). ``None`` keeps
        the client in unauthenticated mode, which is enough to read
        ``Sonoff.GetDeviceInfo`` and to observe the 401 challenge.
    user:
        Always ``"admin"`` on stock firmware; exposed for completeness.
    """

    def __init__(
        self,
        host: str,
        password: Optional[str] = None,
        *,
        port: int = 80,
        path: str = "/rpc",
        user: str = "admin",
        timeout: float = 30.0,
        ssl: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path
        self.user = user
        self.password = password
        self.timeout = timeout
        self.ssl = ssl

        self._ws: Any = None
        self._reader_task: Optional[asyncio.Task] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._challenge: Optional[AuthChallenge] = None
        self._realm: str = ""
        self._nc = 0
        self._device_id: Optional[str] = None
        self._listeners: List[NotificationHandler] = []
        self._queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

    # ------------------------------------------------------------------ props
    @property
    def uri(self) -> str:
        scheme = "wss" if self.ssl else "ws"
        return f"{scheme}://{self.host}:{self.port}{self.path}"

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._reader_task is not None and not self._reader_task.done()

    @property
    def device_id(self) -> Optional[str]:
        return self._device_id

    # -------------------------------------------------------------- lifecycle
    async def connect(self) -> "RpcClient":
        """Open the WebSocket and start the background reader."""
        if self.connected:
            return self
        try:
            self._ws = await _ws_connect(
                self.uri,
                open_timeout=self.timeout,
                ping_interval=20,
                ping_timeout=20,
                max_size=None,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a library error
            raise ConnectionFailed(f"cannot connect to {self.uri}: {exc}") from exc
        self._reader_task = asyncio.create_task(self._reader(), name="sonoff-rpc-reader")
        return self

    async def close(self) -> None:
        """Close the socket and cancel the reader."""
        ws, self._ws = self._ws, None
        task, self._reader_task = self._reader_task, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._fail_pending(ConnectionFailed("connection closed"))

    async def __aenter__(self) -> "RpcClient":
        return await self.connect()

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------ listeners
    def add_listener(self, handler: NotificationHandler) -> None:
        """Register a callback invoked for every server notification frame."""
        self._listeners.append(handler)

    def remove_listener(self, handler: NotificationHandler) -> None:
        if handler in self._listeners:
            self._listeners.remove(handler)

    async def notifications(self):
        """Async iterator yielding raw notification dicts as they arrive."""
        while True:
            yield await self._queue.get()

    # ------------------------------------------------------------------- call
    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invoke ``method`` and return its ``result`` dict.

        Raises :class:`~sonoff_cam.exceptions.RpcError` (or a subclass) on error.
        The digest challenge is answered transparently on the first 401.
        """
        await self._ensure_connected()
        params = params or {}

        for attempt in range(2):
            message = self._build_message(method, params)
            response = await self._send_and_wait(message)
            error = response.get("error")
            if not error:
                return response.get("result", {}) or {}

            err = error_from_payload(error, method)
            challenge = AuthChallenge.from_payload(err.data) if err.data else None
            if isinstance(err, AuthenticationError) and challenge and attempt == 0:
                if self.password is None:
                    raise AuthenticationError(
                        err.code,
                        "device requires a password; pass password=... to authenticate",
                        data=err.data,
                        method=method,
                    )
                await self._apply_challenge(challenge)
                continue
            raise err

        raise ProtocolError(f"authentication loop for {method}")  # pragma: no cover

    # ------------------------------------------------------------- internals
    async def _ensure_connected(self) -> None:
        if not self.connected:
            await self.connect()

    def _build_message(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._next_id += 1
        message: Dict[str, Any] = {
            "method": method,
            "id": self._next_id,
            "params": params,
            "src": "web",
            "jsonrpc": "2.0",
        }
        if self.password and self._challenge and method not in NO_AUTH_METHODS:
            self._nc += 1
            realm = self._realm or self._challenge.realm
            message["auth"] = build_auth(
                method,
                self.password,
                self._challenge,
                nc=self._nc,
                user=self.user,
                realm=realm,
            )
        return message

    async def _send_and_wait(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if self._ws is None:
            raise ConnectionFailed("socket is not open")
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[message["id"]] = future
        try:
            await self._ws.send(json.dumps(message))
            try:
                return await asyncio.wait_for(future, timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                raise Timeout(f"{message['method']} timed out after {self.timeout}s") from exc
        finally:
            self._pending.pop(message["id"], None)

    async def _apply_challenge(self, challenge: AuthChallenge) -> None:
        """Store the challenge and resolve a missing realm from the device id."""
        self._challenge = challenge
        self._nc = 0
        if not challenge.realm:
            if self._device_id is None:
                await self._fetch_device_id()
            self._realm = self._device_id or ""
        else:
            self._realm = challenge.realm

    async def _fetch_device_id(self) -> None:
        """Read the device id (used as the digest realm) pre-authentication."""
        response = await self._send_and_wait(
            {
                "method": _BOOTSTRAP_METHOD,
                "id": self._bootstrap_id(),
                "params": {},
                "src": "web",
                "jsonrpc": "2.0",
            }
        )
        result = response.get("result") or {}
        self._device_id = result.get("id")

    def _bootstrap_id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def _reader(self) -> None:
        ws = self._ws
        assert ws is not None
        try:
            async for raw in ws:
                self._dispatch(raw)
        except ConnectionClosed:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - malformed frame must not kill the reader
            pass
        finally:
            self._fail_pending(ConnectionFailed("connection closed"))

    def _dispatch(self, raw: Any) -> None:
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(message, dict):
            return

        message_id = message.get("id")
        if message_id is not None and message_id in self._pending:
            future = self._pending.pop(message_id)
            if not future.done():
                future.set_result(message)
            return

        if "method" in message:
            self._emit_notification(message)

    def _emit_notification(self, message: Dict[str, Any]) -> None:
        self._queue.put_nowait(message)
        for handler in list(self._listeners):
            try:
                result = handler(message)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception:  # noqa: BLE001 - a bad listener must not break the reader
                pass

    def _fail_pending(self, exc: Exception) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()
