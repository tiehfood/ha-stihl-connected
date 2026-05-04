"""Parser for STIHL Connected BLE advertisements.

Decodes the 20-byte STIHL manufacturer-data block (company ID 0x03DD) into
a structured `StihlAdvertisement` dataclass. Pure-python, no HA imports —
testable in isolation.

Field layouts and semantics are taken from the decompiled official app
(de.stihl.stihlconnected) — see STIHL_BLE_PROTOCOL.md for citations.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

from .const import FAMILY_TABLE, V6_PROTOCOLS

_BC2_OPMODE = ("POWER_OFF", "STAND_BY", "CHARGING", "DISCHARGING")
_BC2_BMS = (
    "FROZEN_ALARM", "FROZEN", "COLD", "PERFECT", "HOT", "HOT_ALARM",
    "FATAL_ERROR", "RFU_7",
)
_BC2_HW_ERR = ("OK", "FACTORY_RESET_DONE", "EXT_FLASH_NOT_AVAIL", "RFU")
_BC2_BC_STATE = ("WORKING_PROPERLY", "RFU_01", "RFU_10", "RFU_11")


def _soh_category(soh_pct: int) -> str:
    """Mirror StateOfHealthKt.asStateOfHealth() in the official app."""
    if soh_pct >= 90:
        return "EXCELLENT"
    if soh_pct >= 75:
        return "GOOD"
    if soh_pct >= 60:
        return "MEDIUM"
    return "BAD"
_APX_LED = ("LED_OFF", "LED_1_ON", "LED_1_TO_2", "LED_1_TO_3", "LED_1_TO_4")
_APX_BMS = _BC2_OPMODE
_ARX_LED = (
    "LED_OFF", "LED_1_ON", "LED_1_TO_2", "LED_1_TO_3",
    "LED_1_TO_4", "LED_1_TO_5", "LED_1_TO_6", "LED_RFU",
)


@dataclass(frozen=True)
class StihlAdvertisement:
    """Decoded STIHL advertisement payload."""

    family: str
    model: str
    label: str
    serial: str  # canonical "device id" — serial for BC2/IC72v, MAC otherwise
    raw: bytes
    sw_version: str | None = None
    hw_version: str | None = None
    sensors: dict[str, Any] = field(default_factory=dict)
    booleans: dict[str, bool] = field(default_factory=dict)


def _u32le(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _s8(b: int) -> int:
    return b - 256 if b >= 128 else b


def _mac(buf: bytes, lo: int, hi: int) -> str:
    return ":".join(f"{b:02X}" for b in reversed(buf[lo:hi]))


def _serial_decimal(buf: bytes, lo: int, hi: int) -> str:
    rev = bytes(reversed(buf[lo:hi]))
    return f"{int.from_bytes(rev, 'big'):010d}"


def _identify(buf: bytes) -> tuple[str, str, str] | None:
    if len(buf) < 12:
        return None
    pid = buf[0]
    prod = buf[1] if pid in V6_PROTOCOLS else buf[11]
    return FAMILY_TABLE.get((pid, prod))


def parse(data: bytes) -> StihlAdvertisement | None:
    """Decode a STIHL manufacturer-data block. Returns None if unrecognised."""
    if len(data) != 20:
        return None
    fam_info = _identify(data)
    if fam_info is None:
        return None
    family, label, model = fam_info
    return _DISPATCH[family](data, family, label, model)


# ---------------------------------------------------------------------------
# Per-family decoders
# ---------------------------------------------------------------------------

def _decode_sc1(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    s = buf[17]
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 1, 7), raw=buf,
        sw_version=f"{buf[15]}.{buf[14]:02d}",
        hw_version=f"{buf[13]}.{buf[12]:02d}",
        sensors={
            "voltage": round(buf[18] * 0.05, 2),
            "temperature": _s8(buf[19]),
            "tx_power": _s8(buf[16]),
            "total_runtime": _u32le(buf, 7),
        },
        booleans={
            "is_connectable": bool(s & 0x01),
            "sw_error": bool(s & 0x02),
            "hw_error": bool(s & 0x04),
        },
    )


def _decode_arx000(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    s = buf[17]
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 1, 7), raw=buf,
        sw_version=f"{buf[15]}.{buf[14]:02d}",
        hw_version=f"{buf[13]}.{buf[12]:02d}",
        sensors={
            "voltage": round(buf[18] * 0.25, 2),
            "temperature": _s8(buf[19]),
            "tool_id": buf[16],
            "total_runtime": _u32le(buf, 7),
            "led": _ARX_LED[(s & 0xE0) >> 5],
        },
        booleans={
            "is_connectable": bool(s & 0x01),
            "sw_error": bool(s & 0x02),
            "hw_error": bool(s & 0x04),
            "bms_com_error": bool(s & 0x08),
        },
    )


def _decode_sc2a(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    cs, ds, ui, ev = buf[12], buf[13], buf[14], buf[15]
    minor, major = buf[18], buf[19]
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 1, 7), raw=buf,
        sw_version=f"{major}.{minor:02d}",
        sensors={
            "tx_power": _s8(buf[17]),
            "total_runtime": _u32le(buf, 7),
        },
        booleans={
            "security_active": (minor % 2 == 0),
            # connectorStatus
            "security_linked": bool(cs & 0x01),
            "reduced_feature_mode": bool(cs & 0x02),
            "rtc_out_of_sync": bool(cs & 0x04),
            "attached_to_other_machine": bool(cs & 0x08),
            "coin_cell_error": bool(cs & 0x10),
            "security_linking_requested": bool(cs & 0x20),
            "hw_error": bool(cs & 0x40),
            "virtual_mark_set": bool(cs & 0x80),
            # dataStorageStatus
            "runtime_history_avail": bool(ds & 0x01),
            "event_history_avail": bool(ds & 0x02),
            "raw_data_avail": bool(ds & 0x04),
            "data_sync_older_24h": bool(ds & 0x20),
            "machine_linked": bool(ds & 0x40),
            "machine_serial_avail": bool(ds & 0x80),
            # ui status
            "message_available": bool(ui & 0x01),
            "error_indication": bool(ui & 0x02),
            "button_pressed_15s": bool(ui & 0x80),
            # event indicator
            "event_error": bool(ev & 0x01),
            "event_maintenance": bool(ev & 0x02),
            "event_usage": bool(ev & 0x04),
            "event_misc": bool(ev & 0x08),
            "event_silent": bool(ev & 0x10),
            "maintenance_due": bool(ev & 0x20),
            "change_battery": bool(ev & 0x40),
            "error_notifier_active": bool(ev & 0x80),
        },
    )


def _decode_apx00(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    soh_bms = buf[16]
    s = buf[17]
    led_idx = (s & 0xE0) >> 5
    soh_pct = (soh_bms & 0x3F) + 40
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 1, 7), raw=buf,
        sw_version=f"{buf[15]}.{buf[14]:02d}",
        hw_version=f"{buf[13]}.{buf[12]:02d}",
        sensors={
            "state_of_health": soh_pct,
            "state_of_health_category": _soh_category(soh_pct),
            "operation_mode": _APX_BMS[(soh_bms & 0xC0) >> 6],
            "voltage": round(buf[18] * 0.25, 2),
            "temperature": _s8(buf[19]),
            "led": _APX_LED[led_idx] if led_idx < len(_APX_LED) else f"LED_RFU_{led_idx}",
            "total_runtime": _u32le(buf, 7),
        },
        booleans={
            "is_connectable": bool(s & 0x01),
            "hw_error": bool(s & 0x02),
            "com_issue": bool(s & 0x04),
            "short_press_event": bool(s & 0x10),
        },
    )


def _decode_bc2(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    bms = buf[7]
    soh = buf[8]
    cstat = buf[14]
    minor, major = buf[18], buf[19]
    soh_pct = (soh & 0x3F) + 40
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_serial_decimal(buf, 2, 7), raw=buf,
        sw_version=f"{major}.{minor:02d}",
        sensors={
            "state_of_charge": buf[17] & 0x7F,
            "state_of_health": soh_pct,
            "state_of_health_category": _soh_category(soh_pct),
            "operation_mode": _BC2_OPMODE[bms & 0x03],
            "bms_thermal_state": _BC2_BMS[(bms & 0x1C) >> 2],
            "bms_hw_sw_error": _BC2_HW_ERR[(cstat & 0x30) >> 4],
            "bc_state": _BC2_BC_STATE[(cstat & 0xC0) >> 6],
            "tool_id": (buf[16] << 8) | buf[15],
            "total_runtime": _u32le(buf, 9),
        },
        booleans={
            "low_voltage": bool(bms & 0x20),
            "button_pressed_15s": bool(bms & 0x40),
            "motor_running": bool(bms & 0x80),
            "history_event_avail": bool(buf[13] & 0x01),
            "history_charge_avail": bool(buf[13] & 0x02),
            "history_discharge_avail": bool(buf[13] & 0x04),
            "history_standby_avail": bool(buf[13] & 0x08),
            "rtc_out_of_sync": bool(cstat & 0x01),
            "security_linked": bool(cstat & 0x02),
            "security_linking_requested": bool(cstat & 0x04),
            "data_sync_older_24h": bool(cstat & 0x08),
            "security_active": (minor % 2 == 0),
        },
    )


def _decode_ic72v(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    cs, ds, ev = buf[12], buf[13], buf[15]
    minor, major = buf[18], buf[19]
    # IC72V's 6-byte "serial" range is actually the BLE MAC (same bytes that
    # appear as the BLE peripheral address). Show it as a MAC, not as a
    # 15-digit decimal — that decimal is just the MAC reformatted and
    # duplicates the "Bluetooth" device-info field. The mower's product
    # serial number (what the official app shows) lives in the linked-machine
    # GATT characteristic and is only readable in phase-2 active mode.
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 2, 8), raw=buf,
        sw_version=f"{major}.{minor:02d}",
        sensors={
            "motor_runtime": _u32le(buf, 8),
            "tx_power": buf[16],
            "debug": buf[17],
        },
        booleans={
            "rtc_out_of_sync": bool(cs & 0x01),
            "security_linking_requested": bool(cs & 0x02),
            "reduced_feature_temperature": bool(cs & 0x04),
            "master_changed": bool(cs & 0x08),
            "reduced_feature_battery": bool(cs & 0x10),
            "button_pressed_15s": bool(cs & 0x20),
            "hw_error": bool(cs & 0x40),
            "virtual_mark_set": bool(cs & 0x80),
            "machine_linked": bool(ds & 0x01),
            "machine_serial_avail": bool(ds & 0x02),
            "data_avail": bool(ds & 0x04),
            "data_sync_older_24h": bool(ds & 0x08),
            "security_linked": bool(ds & 0x10),
            "maintenance_due": bool(ev & 0x20),
            "error_notifier_active": bool(ev & 0x80),
            "security_active": (minor % 2 == 0),
        },
    )


def _decode_sc1mp(buf: bytes, family: str, label: str, model: str) -> StihlAdvertisement:
    s = buf[12]
    minor, major = buf[18], buf[19]
    return StihlAdvertisement(
        family=family, model=model, label=label,
        serial=_mac(buf, 2, 8), raw=buf,
        sw_version=f"{major}.{minor:02d}",
        sensors={
            "voltage": round(buf[13] * 0.05, 2),
            "temperature": _s8(buf[14]),
            "tx_power": _s8(buf[17]),
            "motor_runtime": _u32le(buf, 8),
        },
        booleans={
            "security_linked": bool(s & 0x01),
            "security_linking_requested": bool(s & 0x02),
            "reduced_feature_mode": bool(s & 0x04),
            "rtc_out_of_sync": bool(s & 0x08),
            "data_avail_in_storage": bool(s & 0x10),
            "data_sync_older_24h": bool(s & 0x20),
            "hw_error": bool(s & 0x40),
            "service_needed": bool(s & 0x80),
            "security_active": (minor % 2 == 0),
        },
    )


_DISPATCH = {
    "SC1": _decode_sc1,
    "ARX000": _decode_arx000,
    "SC2A": _decode_sc2a,
    "APX00": _decode_apx00,
    "BC2": _decode_bc2,
    "IC72V": _decode_ic72v,
    "SC1MP": _decode_sc1mp,
}
