"""Minimal async ONVIF PullPoint client for the CAM-S2 motion/person events.

The stock firmware publishes three boolean-state topics over ONVIF and this is
the only event source observed to deliver data (the RPC ``NotifyEvent`` push
stream never fired during testing). Authentication is a WS-Security
``UsernameToken`` built from the *RTSP* credentials, and ``SOAPAction`` must not
carry the ``/...Request`` suffix the WSDL implies: see ``docs/PROTOCOL.md`` in
the reference project for the full write-up.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import aiohttp

from .const import (
    ONVIF_EVENTS_PATH,
    ONVIF_MAX_RECONNECT_DELAY,
    ONVIF_PORT_TYPE,
    ONVIF_PULL_MESSAGE_LIMIT,
    ONVIF_PULL_TIMEOUT,
    ONVIF_RECONNECT_DELAY,
    ONVIF_SUBSCRIPTION_LIFETIME,
)
from .sonoff_cam.exceptions import ProtocolError

_LOGGER = logging.getLogger(__name__)

ENVELOPE_NS = (
    'xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:tev="http://www.onvif.org/ver10/events/wsdl" '
    'xmlns:wsa5="http://www.w3.org/2005/08/addressing" '
    'xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" '
    'xmlns:tt="http://www.onvif.org/ver10/schema"'
)

_TOPIC_RE = re.compile(r"<wsnt:Topic[^>]*>([^<]+)")
_ITEM_RE = re.compile(r'<tt:SimpleItem Name="([^"]+)" Value="([^"]*)"')
_ADDRESS_RE = re.compile(r"<wsa:Address>([^<]+)</wsa:Address>")
_MSG_RE = re.compile(r"<wsnt:NotificationMessage>(.*?)</wsnt:NotificationMessage>", re.S)

#: Topic used for any detected motion.
MOTION_TOPICS = (
    "tns1:VideoSource/MotionAlarm",
    "tns1:RuleEngine/CellMotionDetector/Motion",
)
#: Topic used for AI person detection.
PERSON_TOPIC = "tns1:RuleEngine/MyRuleDetector/PeopleDetect"

EVENT_MOTION = "motion"
EVENT_PERSON = "person"

EventHandler = Callable[[str, bool], Any]


class OnvifEventClient:
    """Pull ONVIF events and hand decoded ``(kind, state)`` pairs to a callback."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        handler: EventHandler,
        *,
        port: int = 80,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._handler = handler
        # The camera closes the HTTP connection after each response. A shared
        # keep-alive session then POSTs on a dead socket, so force a fresh TCP
        # connection for every ONVIF request.
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(force_close=True)
        )

    # ------------------------------------------------------------------ wssec
    def _security_header(self) -> str:
        nonce = os.urandom(16)
        created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        digest = base64.b64encode(
            hashlib.sha1(nonce + created.encode() + self._password.encode()).digest()
        ).decode()
        return (
            '<s:Header><Security s:mustUnderstand="1" '
            'xmlns="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            f"<UsernameToken><Username>{self._username}</Username>"
            '<Password Type="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
            f"{digest}</Password>"
            '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
            f"{base64.b64encode(nonce).decode()}</Nonce>"
            '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-utility-1.0.xsd">'
            f"{created}</Created></UsernameToken></Security></s:Header>"
        )

    async def _call(self, path: str, body: str, action: str) -> str:
        envelope = (
            f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope {ENVELOPE_NS}>'
            f"{self._security_header()}<s:Body>{body}</s:Body></s:Envelope>"
        )
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": action,
        }
        url = f"http://{self._host}:{self._port}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with self._session.post(
            url, data=envelope.encode(), headers=headers, timeout=timeout
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise ProtocolError(
                    f"ONVIF {action} returned HTTP {response.status}: {text[:200]}"
                )
            if "<Fault" in text or ":Fault>" in text:
                raise ProtocolError(f"ONVIF {action} returned a SOAP fault: {text[:200]}")
            return text

    async def _subscribe(self) -> str:
        response = await self._call(
            ONVIF_EVENTS_PATH,
            "<tev:CreatePullPointSubscription>"
            f"<tev:InitialTerminationTime>{ONVIF_SUBSCRIPTION_LIFETIME}"
            "</tev:InitialTerminationTime></tev:CreatePullPointSubscription>",
            f"{ONVIF_PORT_TYPE}/CreatePullPointSubscription",
        )
        match = _ADDRESS_RE.search(response)
        if not match:
            raise ProtocolError(f"no subscription address in ONVIF reply: {response[:300]}")
        # The device may include a scheme, host and port; only the path is
        # usable because _call() targets the camera directly.
        parsed = urlparse(match.group(1))
        path = parsed.path or ""
        if parsed.query:
            path = f"{path}?{parsed.query}"
        if not path:
            raise ProtocolError(f"invalid ONVIF subscription address: {match.group(1)}")
        return path

    async def _pull(self, path: str) -> list[tuple[str, bool]]:
        response = await self._call(
            path,
            "<tev:PullMessages>"
            f"<tev:Timeout>{ONVIF_PULL_TIMEOUT}</tev:Timeout>"
            f"<tev:MessageLimit>{ONVIF_PULL_MESSAGE_LIMIT}</tev:MessageLimit>"
            "</tev:PullMessages>",
            f"{ONVIF_PORT_TYPE}/PullMessages",
        )
        if "<Fault" in response or ":Fault>" in response:
            raise ProtocolError(f"ONVIF PullMessages returned a SOAP fault: {response[:200]}")
        events: list[tuple[str, bool]] = []
        for block in _MSG_RE.findall(response):
            topic_match = _TOPIC_RE.search(block)
            if not topic_match:
                continue
            items = dict(_ITEM_RE.findall(block))
            state = str(items.get("State", "")).strip().lower() == "true"
            topic = topic_match.group(1)
            kind = _kind_for_topic(topic)
            if kind is not None:
                events.append((kind, state))
        return events

    async def _unsubscribe(self, path: str) -> None:
        """Best-effort removal of a pull-point subscription."""
        try:
            await self._call(path, "<wsnt:Unsubscribe/>", f"{ONVIF_PORT_TYPE}/Unsubscribe")
        except Exception as err:
            _LOGGER.debug("ONVIF unsubscribe failed: %s", err)

    async def async_run(self) -> None:
        """Run the subscription loop until the task is cancelled."""
        sub_path: str | None = None
        delay = ONVIF_RECONNECT_DELAY
        try:
            while True:
                try:
                    if sub_path is None:
                        sub_path = await self._subscribe()
                        _LOGGER.debug("ONVIF subscription created at %s", sub_path)
                    events = await self._pull(sub_path)
                    for kind, state in events:
                        self._handler(kind, state)
                    delay = ONVIF_RECONNECT_DELAY
                    if not events:
                        # Some devices answer PullMessages immediately with an
                        # empty body. Never busy-loop against the camera.
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    raise
                except ProtocolError as err:
                    # A SOAP fault / 4xx means the subscription is no longer
                    # usable. Drop it and create a new one.
                    _LOGGER.debug("ONVIF subscription error, renewing in %ss: %s", delay, err)
                    if sub_path is not None:
                        await self._unsubscribe(sub_path)
                    sub_path = None
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, ONVIF_MAX_RECONNECT_DELAY)
                except (aiohttp.ClientError, TimeoutError, OSError) as err:
                    # Transport errors do not invalidate the subscription. Keep
                    # it and retry, avoiding a subscription leak.
                    _LOGGER.debug("ONVIF transport error, retrying in %ss: %s", delay, err)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, ONVIF_MAX_RECONNECT_DELAY)
                except Exception as err:
                    _LOGGER.debug("ONVIF event error, reconnecting in %ss: %s", delay, err)
                    if sub_path is not None:
                        await self._unsubscribe(sub_path)
                    sub_path = None
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, ONVIF_MAX_RECONNECT_DELAY)
        finally:
            if sub_path is not None:
                with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(self._unsubscribe(sub_path), timeout=5)
            with contextlib.suppress(asyncio.CancelledError):
                await self._session.close()


def _kind_for_topic(topic: str) -> str | None:
    if topic in MOTION_TOPICS:
        return EVENT_MOTION
    if topic == PERSON_TOPIC:
        return EVENT_PERSON
    return None
