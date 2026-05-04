"""Shared helpers for STIHL Connected entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .parser import StihlAdvertisement


def display_serial(adv: StihlAdvertisement) -> str:
    """Serial as the official Stihl app shows it (no leading zeros)."""
    s = adv.serial
    if s.isdigit():
        s2 = s.lstrip("0")
        return s2 or "0"
    return s


def device_name(adv: StihlAdvertisement) -> str:
    return f"STIHL {adv.label} {display_serial(adv)}"


def make_device_info(
    adv: StihlAdvertisement,
    address: str,
    gatt_device_info: dict[str, str] | None = None,
) -> DeviceInfo:
    """Build DeviceInfo, preferring strings from GATT DeviceInfo when present."""
    gatt = gatt_device_info or {}
    info: DeviceInfo = {
        "identifiers": {(DOMAIN, address)},
        "manufacturer": "STIHL",
        "model": gatt.get("model_number") or adv.model,
        "name": device_name(adv),
        "serial_number": display_serial(adv),
    }
    sw = gatt.get("sw_revision") or adv.sw_version
    if sw:
        info["sw_version"] = sw
    hw = gatt.get("hw_revision") or adv.hw_version
    if hw:
        info["hw_version"] = hw
    return info
