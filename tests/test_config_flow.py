"""Config flow tests for the SONOFF CAM-S2 (Local) integration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sonoff_cam_local.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    DOMAIN,
)

from .fakes import DEVICE_ID, PASSWORD, FakeSonoffCamera, UnreachableSonoffCamera

USER_INPUT = {CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: PASSWORD}


def _patch(camera=FakeSonoffCamera):
    """Patch both the flow's and the coordinator's client with ``camera``."""
    return (
        patch("custom_components.sonoff_cam_local.config_flow.SonoffCamera", camera),
        patch("custom_components.sonoff_cam_local.coordinator.SonoffCamera", camera),
    )


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _manual_form(hass: HomeAssistant):
    """Start the flow and open the manual-entry form."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )


async def test_user_flow_menu(hass: HomeAssistant) -> None:
    """The user flow offers manual entry and a network scan."""
    result = await _start(hass)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"manual", "scan"}


async def test_user_flow_success(hass: HomeAssistant) -> None:
    """A valid form creates a config entry."""
    flow_patch, coordinator_patch = _patch()
    with flow_patch, coordinator_patch:
        result = await _manual_form(hass)
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CAM-S2"
    assert result["data"][CONF_HOST] == "192.168.1.100"


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """A wrong password shows an error and does not create the entry."""
    flow_patch, coordinator_patch = _patch()
    with flow_patch, coordinator_patch:
        result = await _manual_form(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant) -> None:
    """An unreachable camera shows cannot_connect."""
    flow_patch, coordinator_patch = _patch(UnreachableSonoffCamera)
    with flow_patch, coordinator_patch:
        result = await _manual_form(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_password_required(hass: HomeAssistant) -> None:
    """A camera that needs auth prompts for a password."""
    flow_patch, coordinator_patch = _patch()
    with flow_patch, coordinator_patch:
        result = await _manual_form(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.168.1.100", CONF_PORT: 80, CONF_PASSWORD: ""},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "password_required"}


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    """Adding the same camera twice aborts."""
    entry = MockConfigEntry(domain=DOMAIN, title="CAM-S2", data=USER_INPUT, unique_id=DEVICE_ID)
    entry.add_to_hass(hass)

    flow_patch, coordinator_patch = _patch()
    with flow_patch, coordinator_patch:
        result = await _manual_form(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_scan_flow_lists_cameras(hass: HomeAssistant) -> None:
    """The scan step lists discovered cameras and configures the chosen one."""
    flow_patch, coordinator_patch = _patch()
    with (
        flow_patch,
        coordinator_patch,
        patch(
            "custom_components.sonoff_cam_local.config_flow._scan_network",
            return_value=["192.168.1.100", "192.168.1.101"],
        ),
    ):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "scan"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "scan"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.100"}
        )
        # The fake camera needs a password, so the flow asks for it next.
        assert result["step_id"] == "dhcp_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: PASSWORD}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.168.1.100"
