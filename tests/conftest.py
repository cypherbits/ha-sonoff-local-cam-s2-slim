"""Shared pytest fixtures for the SONOFF CAM-S2 (Local) tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load this custom integration in tests."""
    yield
