"""Shared pytest fixtures for the SONOFF CAM-S2 (Local) tests."""

from __future__ import annotations

import asyncio

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load this custom integration in tests."""
    yield


@pytest.fixture(autouse=True)
def fake_onvif_client(monkeypatch):
    """Keep the ONVIF background task off the network during tests."""

    class _FakeOnvifClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def async_run(self) -> None:
            await asyncio.sleep(3600)

    monkeypatch.setattr(
        "custom_components.sonoff_cam_local.coordinator.OnvifEventClient",
        _FakeOnvifClient,
    )
    yield
