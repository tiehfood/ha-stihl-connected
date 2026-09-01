"""Active GATT reads for STIHL Connected.

Read-only. No authentication / no signing — works without the device-paired
ECDSA-P256 keypair from the official Stihl Cloud account.

Per family we read a curated subset of high-value characteristics:
  - DeviceInfo (0x180A)        : model, hw rev, sw rev (strings)
  - ConnectorInfo SC2A         : coin cell voltage, RTC, linked machine serial
  - ConnectorInfo BC2          : RTC (no coin cell on this variant)
  - BatterySettings BC2        : charge mode, storage charge, silent-charge schedule
  - MachineInfo SC2A           : live battery V/I, motor RPM, motor runtime,
                                  tool ID, battery state indicator
  - MachineInfo v72 (IC72V)    : dual-battery voltage, input current, motor &
                                  electronics temperature, runtimes, start counts

APX00 and ARX000 only expose DeviceInfo. The ConnectorInfo temperatures are
read but not exposed yet — see `_unresolved`.
"""
from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice

try:
    from bleak_retry_connector import establish_connection  # type: ignore
except ImportError:  # pragma: no cover — fallback if dep missing
    establish_connection = None  # type: ignore

_LOGGER = logging.getLogger(__name__)

# ---- Standard Device Information (0x180A) ----------------------------------
DIS_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
DIS_HW_REV = "00002a27-0000-1000-8000-00805f9b34fb"
DIS_SW_REV = "00002a28-0000-1000-8000-00805f9b34fb"

# ---- ConnectorInfo BC2 (E180...) -------------------------------------------
# The BC2 variant has no coin-cell-voltage characteristic, so its numbering is
# NOT the SC2A numbering shifted — E1800001 is already the env temperature.
BC2_CI_ENV_TEMP = "e1800001-d696-449b-8516-9970e85e4148"
BC2_CI_MIN_MAX_TEMP = "e1800002-d696-449b-8516-9970e85e4148"
BC2_CI_UNIX_TIME = "e1800003-d696-449b-8516-9970e85e4148"
BC2_CI_CONNECTOR_STATUS = "e1800004-d696-449b-8516-9970e85e4148"
BC2_CI_DATA_STORAGE_STATUS = "e1800005-d696-449b-8516-9970e85e4148"

# ---- ConnectorInfo SC2A (6CBB...) ------------------------------------------
SC2A_CI_COIN_CELL_VOLTAGE = "6cbb0001-3309-4730-982c-92a66e13bdc4"
SC2A_CI_ENV_TEMP = "6cbb0002-3309-4730-982c-92a66e13bdc4"
SC2A_CI_MIN_MAX_TEMP = "6cbb0003-3309-4730-982c-92a66e13bdc4"
SC2A_CI_UNIX_TIME = "6cbb0004-3309-4730-982c-92a66e13bdc4"
SC2A_CI_LINKED_MACHINE_SERIAL = "6cbb000a-3309-4730-982c-92a66e13bdc4"

# ---- BatterySettings BC2 (4B188...) ----------------------------------------
BC2_BS_CHARGE_MODE = "4b188001-d250-49f0-9f7f-81e677279c39"
BC2_BS_STORAGE_CHARGE_MODE = "4b188002-d250-49f0-9f7f-81e677279c39"
BC2_BS_SIL_CHARGE_MODE = "4b188003-d250-49f0-9f7f-81e677279c39"

# ---- MachineInfo SC2A (8E58...) --------------------------------------------
SC2A_MI_LAST_SEEN_MACHINE_SERIAL = "8e580002-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_BATTERY_VOLTAGE = "8e580003-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_TOOL_ID = "8e580007-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_MASTER_MOTOR_RUNTIME = "8e580008-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_MASTER_MOTOR_SPEED = "8e580009-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_BATTERY_CURRENT = "8e58000b-3b28-4145-9213-f0646c15ab5e"
SC2A_MI_BATTERY_STATE_INDICATOR = "8e58000e-3b28-4145-9213-f0646c15ab5e"

# ---- MachineInfo v72 (IC72V) — own layout, see _V72_READS ------------------
V72_MI_MASTER_INPUT_CURRENT = "8e58000f-3b28-4145-9213-f0646c15ab5e"
V72_MI_BATTERY_VOLTAGE_HIGH = "8e580010-3b28-4145-9213-f0646c15ab5e"
V72_MI_BATTERY_VOLTAGE_LOW = "8e580011-3b28-4145-9213-f0646c15ab5e"
V72_MI_MASTER_ELEC_RUNTIME = "8e580014-3b28-4145-9213-f0646c15ab5e"
V72_MI_MASTER_MOTOR_START_COUNT = "8e580015-3b28-4145-9213-f0646c15ab5e"
V72_MI_MASTER_ELEC_START_COUNT = "8e580017-3b28-4145-9213-f0646c15ab5e"
V72_MI_MASTER_MOTOR_TEMPERATURE = "8e580018-3b28-4145-9213-f0646c15ab5e"
V72_MI_MASTER_ELEC_TEMPERATURE = "8e580019-3b28-4145-9213-f0646c15ab5e"


# ---------------------------------------------------------------------------
# decoders — return None on failure so the merge step can skip the field
# ---------------------------------------------------------------------------

def _u8(b: bytes) -> int | None:
    return b[0] if b else None


def _u16le(b: bytes) -> int | None:
    return struct.unpack_from("<H", b)[0] if len(b) >= 2 else None


def _s16le(b: bytes) -> int | None:
    return struct.unpack_from("<h", b)[0] if len(b) >= 2 else None


def _u32le(b: bytes) -> int | None:
    return struct.unpack_from("<I", b)[0] if len(b) >= 4 else None


def _ascii(b: bytes) -> str | None:
    if not b:
        return None
    s = b.decode("utf-8", errors="replace").rstrip("\x00").strip()
    return s or None


def _unresolved(b: bytes) -> None:
    """Read the characteristic but expose nothing.

    The ConnectorInfo temperatures are 16-bit values whose scale factor is not
    derivable from the app (it never renders them). Reading them still puts the
    raw bytes in the debug log, which is what settles the scale — see issue #1.
    """
    return None


def _charge_mode(b: bytes) -> str | None:
    v = _u8(b)
    return None if v is None else {0: "normal", 2: "rapid"}.get(v, f"unknown_{v}")


def _storage_mode(b: bytes) -> str | None:
    v = _u8(b)
    return None if v is None else {0: "off", 1: "active"}.get(v, f"unknown_{v}")


def _sil_window(b: bytes) -> str | None:
    if len(b) < 6:
        return None
    sH, sM, _sS, eH, eM, _eS = b[:6]
    return f"{sH:02d}:{sM:02d}-{eH:02d}:{eM:02d}"


def _decode_battery_state_indicator(b: bytes) -> dict[str, bool] | None:
    v = _u8(b)
    if v is None:
        return None
    bits = {
        "indicator_cold": v & 0x01, "indicator_warm": v & 0x02,
        "indicator_hot": v & 0x04, "indicator_alarm": v & 0x08,
        "indicator_fatal_error": v & 0x10, "indicator_frozen": v & 0x20,
        "indicator_temperature_alarm": v & 0x40, "indicator_over_voltage": v & 0x80,
    }
    return {k: bool(v) for k, v in bits.items()}


# ---------------------------------------------------------------------------
# read tasks — one per (uuid, key, decoder, target_dict)
# ---------------------------------------------------------------------------

# (uuid, key, decoder, target) where target is "sensors", "booleans",
# "device_info", "_indicator_bits" (a flat dict of bools to merge) or
# "_unresolved" (read for the debug log, never exposed).
_DIS_READS: list[tuple[str, str, Any, str]] = [
    (DIS_MODEL, "model_number", _ascii, "device_info"),
    (DIS_HW_REV, "hw_revision", _ascii, "device_info"),
    (DIS_SW_REV, "sw_revision", _ascii, "device_info"),
]

_BC2_READS: list[tuple[str, str, Any, str]] = _DIS_READS + [
    (BC2_CI_ENV_TEMP, "env_temperature", _unresolved, "_unresolved"),
    (BC2_CI_MIN_MAX_TEMP, "min_max_temp", _unresolved, "_unresolved"),
    (BC2_CI_UNIX_TIME, "device_unix_time", _u32le, "sensors"),
    (BC2_BS_CHARGE_MODE, "charge_mode", _charge_mode, "sensors"),
    (BC2_BS_STORAGE_CHARGE_MODE, "storage_charge_mode", _storage_mode, "sensors"),
    (BC2_BS_SIL_CHARGE_MODE, "silent_charge_window", _sil_window, "sensors"),
]

# ConnectorInfo is shared verbatim between SC2A and the v72 (IC72V) variant.
_SC2A_CI_READS: list[tuple[str, str, Any, str]] = [
    (SC2A_CI_COIN_CELL_VOLTAGE, "coin_cell_voltage",
     lambda b: round(_u8(b) * 0.05, 2) if _u8(b) is not None else None, "sensors"),
    (SC2A_CI_ENV_TEMP, "env_temperature", _unresolved, "_unresolved"),
    (SC2A_CI_MIN_MAX_TEMP, "min_max_temp", _unresolved, "_unresolved"),
    (SC2A_CI_UNIX_TIME, "device_unix_time", _u32le, "sensors"),
    (SC2A_CI_LINKED_MACHINE_SERIAL, "linked_machine_serial",
     lambda b: str(_u32le(b)) if _u32le(b) else None, "sensors"),
]

_SC2A_READS: list[tuple[str, str, Any, str]] = _DIS_READS + _SC2A_CI_READS + [
    (SC2A_MI_LAST_SEEN_MACHINE_SERIAL, "last_seen_machine_serial",
     lambda b: str(_u32le(b)) if _u32le(b) else None, "sensors"),
    (SC2A_MI_BATTERY_VOLTAGE, "battery_voltage_live",
     lambda b: round((_u16le(b) or 0) / 1000.0, 3) if _u16le(b) is not None else None, "sensors"),
    (SC2A_MI_BATTERY_CURRENT, "battery_current",
     lambda b: round((_s16le(b) or 0) / 1000.0, 3) if _s16le(b) is not None else None, "sensors"),
    (SC2A_MI_TOOL_ID, "linked_tool_id", _u16le, "sensors"),
    (SC2A_MI_MASTER_MOTOR_RUNTIME, "master_motor_runtime", _u32le, "sensors"),
    (SC2A_MI_MASTER_MOTOR_SPEED, "master_motor_speed", _u16le, "sensors"),
    (SC2A_MI_BATTERY_STATE_INDICATOR, "battery_state_indicator",
     _decode_battery_state_indicator, "_indicator_bits"),
]

# The v72 MachineInfo is its own layout, not SC2A plus extras: it has no
# battery voltage / current / state-indicator characteristic, and the shared
# indices carry different fields.
_V72_READS: list[tuple[str, str, Any, str]] = _DIS_READS + _SC2A_CI_READS + [
    (SC2A_MI_LAST_SEEN_MACHINE_SERIAL, "last_seen_machine_serial",
     lambda b: str(_u32le(b)) if _u32le(b) else None, "sensors"),
    (SC2A_MI_TOOL_ID, "linked_tool_id", _u16le, "sensors"),
    (SC2A_MI_MASTER_MOTOR_RUNTIME, "master_motor_runtime", _u32le, "sensors"),
    (SC2A_MI_MASTER_MOTOR_SPEED, "master_motor_speed", _u16le, "sensors"),
    (V72_MI_MASTER_INPUT_CURRENT, "master_input_current",
     lambda b: round((_s16le(b) or 0) / 1000.0, 3) if _s16le(b) is not None else None, "sensors"),
    (V72_MI_BATTERY_VOLTAGE_HIGH, "battery_voltage_high_side",
     lambda b: round((_u16le(b) or 0) / 1000.0, 3) if _u16le(b) is not None else None, "sensors"),
    (V72_MI_BATTERY_VOLTAGE_LOW, "battery_voltage_low_side",
     lambda b: round((_u16le(b) or 0) / 1000.0, 3) if _u16le(b) is not None else None, "sensors"),
    (V72_MI_MASTER_ELEC_RUNTIME, "master_electronic_runtime", _u32le, "sensors"),
    (V72_MI_MASTER_MOTOR_START_COUNT, "master_motor_start_count", _u16le, "sensors"),
    (V72_MI_MASTER_ELEC_START_COUNT, "master_electronic_start_count", _u16le, "sensors"),
    (V72_MI_MASTER_MOTOR_TEMPERATURE, "master_motor_temperature", _s16le, "sensors"),
    (V72_MI_MASTER_ELEC_TEMPERATURE, "master_electronic_temperature", _s16le, "sensors"),
]

# APX00 (protocol 5) and ARX000 (protocol 3) predate the connector services —
# the app has no connector class for either, so only the standard DeviceInfo
# is available. Reads that 404 on a variant are silently dropped.
_READS_BY_FAMILY = {
    "BC2": _BC2_READS,
    "APX00": _DIS_READS,
    "ARX000": _DIS_READS,
    "SC2A": _SC2A_READS,
    "IC72V": _V72_READS,
    "SC1": [],              # no useful active GATT
    "SC1MP": [],
}


# ---------------------------------------------------------------------------
# top-level entry point — single connection, batch reads
# ---------------------------------------------------------------------------

GattExtras = dict[str, Any]


async def read_all(device: BLEDevice, family: str, *,
                   timeout: float = 30.0) -> tuple[GattExtras, GattExtras, GattExtras]:
    """Connect once, read every supported characteristic for the family.

    Returns (sensors, booleans, device_info_extras) — all values are coerced;
    failed reads are silently dropped.
    """
    plan = _READS_BY_FAMILY.get(family, [])
    sensors: GattExtras = {}
    booleans: GattExtras = {}
    device_info: GattExtras = {}
    if not plan:
        return sensors, booleans, device_info

    if establish_connection is not None:
        client = await establish_connection(BleakClient, device, f"stihl-{family}",
                                            max_attempts=2)
    else:
        client = BleakClient(device, timeout=timeout)
        await client.connect()

    try:
        for uuid, key, decoder, target in plan:
            try:
                raw = bytes(await client.read_gatt_char(uuid))
            except Exception as e:
                _LOGGER.debug("read %s failed: %s", uuid, e)
                continue
            _LOGGER.debug("read %s (%s) = %s", key, uuid, raw.hex())
            try:
                value = decoder(raw)
            except Exception as e:
                _LOGGER.debug("decode %s failed (%s): %s", key, e, raw.hex())
                continue
            if value is None:
                continue
            if target == "sensors":
                sensors[key] = value
            elif target == "booleans":
                booleans[key] = bool(value)
            elif target == "device_info":
                device_info[key] = value
            elif target == "_indicator_bits":
                booleans.update(value)  # already dict[str, bool]
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    return sensors, booleans, device_info
