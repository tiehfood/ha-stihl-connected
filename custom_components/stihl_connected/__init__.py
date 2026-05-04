"""STIHL Connected — passive BLE integration."""
from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import StihlActiveBluetoothProcessorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    ble_device = async_ble_device_from_address(hass, address.upper(), connectable=False)
    if ble_device is None:
        raise ConfigEntryNotReady(
            f"Could not find STIHL device with address {address}"
        )

    coordinator = StihlActiveBluetoothProcessorCoordinator(hass, address)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward platform setup FIRST so processors are registered, then start
    # the BLE subscription. Otherwise the first advertisement that arrives
    # before platforms are ready is lost and entities never get created.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
