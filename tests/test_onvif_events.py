"""Tests for the ONVIF event client parsing and fault handling."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.sonoff_cam_local.onvif_events import (
    EVENT_MOTION,
    OnvifEventClient,
)
from custom_components.sonoff_cam_local.sonoff_cam.exceptions import ProtocolError

FAULT = (
    '<s:Envelope><s:Body><s:Fault><faultstring>No subscription</faultstring>'
    "</s:Fault></s:Body></s:Envelope>"
)

EVENT = (
    '<s:Envelope><s:Body><wsnt:NotificationMessage>'
    "<wsnt:Topic>tns1:RuleEngine/CellMotionDetector/Motion</wsnt:Topic>"
    '<wsnt:Message><tt:Message><tt:Data>'
    '<tt:SimpleItem Name="State" Value="true"/>'
    "</tt:Data></tt:Message></wsnt:Message>"
    "</wsnt:NotificationMessage></s:Body></s:Envelope>"
)


def _client(handler: Any = None) -> OnvifEventClient:
    client = object.__new__(OnvifEventClient)
    client._host = "192.168.1.100"
    client._port = 80
    client._username = "sonoff"
    client._password = "secret"
    client._handler = handler or (lambda kind, state: None)
    return client


async def test_pull_raises_on_soap_fault() -> None:
    """A fault body must not be treated as an empty poll."""
    client = _client()

    async def fake_call(path: str, body: str, action: str) -> str:
        return FAULT

    client._call = fake_call  # type: ignore[method-assign]
    with pytest.raises(ProtocolError):
        await client._pull("/onvif/sub")


async def test_pull_parses_motion_event() -> None:
    """A normal NotificationMessage is decoded into (kind, state)."""
    client = _client()

    async def fake_call(path: str, body: str, action: str) -> str:
        return EVENT

    client._call = fake_call  # type: ignore[method-assign]
    assert await client._pull("/onvif/sub") == [(EVENT_MOTION, True)]


async def test_subscribe_keeps_only_the_path() -> None:
    """An address with a port must still become a valid relative path."""
    client = _client()

    async def fake_call(path: str, body: str, action: str) -> str:
        return (
            "<s:Envelope><s:Body><wsa:Address>"
            "http://192.168.1.100:80/onvif/events_service/sub1"
            "</wsa:Address></s:Body></s:Envelope>"
        )

    client._call = fake_call  # type: ignore[method-assign]
    assert await client._subscribe() == "/onvif/events_service/sub1"
