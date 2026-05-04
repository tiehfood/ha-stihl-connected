"""Config flow for STIHL Connected."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, STIHL_MANUFACTURER_ID
from .entity import device_name
from .parser import StihlAdvertisement, parse


def _decode(info: BluetoothServiceInfoBleak) -> StihlAdvertisement | None:
    mfg = info.manufacturer_data.get(STIHL_MANUFACTURER_ID)
    if not mfg:
        return None
    return parse(bytes(mfg))


class StihlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a STIHL Connected config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_adv: StihlAdvertisement | None = None
        self._discovered: dict[str, tuple[BluetoothServiceInfoBleak, StihlAdvertisement]] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        adv = _decode(discovery_info)
        if adv is None:
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        self._discovered_adv = adv
        # Show in HA's "Discovered" list with friendly name.
        self.context["title_placeholders"] = {"name": device_name(adv)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery_info is not None
        assert self._discovered_adv is not None
        if user_input is not None:
            return self.async_create_entry(
                title=device_name(self._discovered_adv),
                data={CONF_ADDRESS: self._discovery_info.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": device_name(self._discovered_adv),
                "address": self._discovery_info.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual flow: pick from already-seen-but-not-yet-configured STIHL devices."""
        if user_input is not None:
            address: str = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            _info, adv = self._discovered[address]
            return self.async_create_entry(
                title=device_name(adv),
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids()
        self._discovered = {}
        for info in async_discovered_service_info(self.hass, connectable=False):
            if info.address in current:
                continue
            adv = _decode(info)
            if adv is None:
                continue
            self._discovered[info.address] = (info, adv)
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            addr: f"{device_name(adv)} ({addr})"
                            for addr, (_, adv) in self._discovered.items()
                        }
                    )
                }
            ),
        )
