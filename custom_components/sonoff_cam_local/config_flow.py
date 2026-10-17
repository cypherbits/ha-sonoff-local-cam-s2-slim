"""Config and options flow for the SONOFF CAM-S2 (Local) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_ENABLE_ONVIF,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_RPC_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .sonoff_cam import SonoffCamera
from .sonoff_cam.exceptions import (
    AuthenticationError,
    ConnectionFailed,
    ProtocolError,
    SonoffCamError,
    Timeout,
)
from .sonoff_cam.models import DeviceInfo

_LOGGER = logging.getLogger(__name__)

_CONNECT_ERRORS = (ConnectionFailed, Timeout, ProtocolError, OSError)


def _host_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): selector.TextSelector(),
            vol.Optional(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=65535, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): (
                selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                )
            ),
        }
    )


def _password_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_PASSWORD, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


class SonoffCamConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a SONOFF CAM-S2."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None

    # --------------------------------------------------------------- helpers
    async def _probe(
        self, host: str, port: int, password: str | None
    ) -> tuple[DeviceInfo | None, str | None]:
        """Connect and validate; returns ``(device_info, error_key)``."""
        client = SonoffCamera(host, password, user=DEFAULT_RPC_USERNAME, port=port, timeout=15.0)
        try:
            await client.connect()
            info = await client.get_device_info(refresh=True)
            if info.auth_enabled and not password:
                return info, "password_required"
            await client.get_status()
            return info, None
        except AuthenticationError:
            return None, "invalid_auth"
        except _CONNECT_ERRORS:
            return None, "cannot_connect"
        except SonoffCamError:
            return None, "unknown"
        finally:
            await client.close()

    async def _async_create(
        self, host: str, port: int, password: str | None, info: DeviceInfo
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(info.device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        return self.async_create_entry(
            title=info.name or info.model or host,
            data={CONF_HOST: host, CONF_PORT: port, CONF_PASSWORD: password or ""},
        )

    # ------------------------------------------------------------------ steps
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            password = user_input.get(CONF_PASSWORD) or None
            info, error = await self._probe(host, port, password)
            if error:
                errors["base"] = error
            elif info is not None:
                return await self._async_create(host, port, password, info)

        return self.async_show_form(
            step_id="user", data_schema=_host_schema(user_input), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            password = user_input.get(CONF_PASSWORD) or None
            info, error = await self._probe(host, port, password)
            if error:
                errors["base"] = error
            elif info is not None:
                await self.async_set_unique_id(info.device_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_PASSWORD: password or ""},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_host_schema({**entry.data, **(user_input or {})}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = entry.data[CONF_HOST]
            port = entry.data.get(CONF_PORT, DEFAULT_PORT)
            password = user_input.get(CONF_PASSWORD) or None
            _info, error = await self._probe(host, port, password)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password or ""}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_password_schema(), errors=errors
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        host = discovery_info.ip
        info, error = await self._probe(host, DEFAULT_PORT, None)
        if error == "cannot_connect" or info is None:
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(info.device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._discovered_host = host
        self.context["title_placeholders"] = {"name": info.name or info.model or host}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered_host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD) or None
            info, error = await self._probe(self._discovered_host, DEFAULT_PORT, password)
            if error:
                errors["base"] = error
            elif info is not None:
                return await self._async_create(self._discovered_host, DEFAULT_PORT, password, info)

        return self.async_show_form(
            step_id="dhcp_confirm", data_schema=_password_schema(), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SonoffCamOptionsFlow()


class SonoffCamOptionsFlow(OptionsFlow):
    """Options: polling interval and ONVIF motion events."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_ENABLE_ONVIF,
                    default=options.get(CONF_ENABLE_ONVIF, True),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
