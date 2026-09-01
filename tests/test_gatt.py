"""Unit tests for the GATT read plans.

Pins every (UUID -> field) pair to the characteristic map of the official app,
so a mis-numbered characteristic can't silently ship again.

Run from repo root:
    ./virtenv/bin/python tests/test_gatt.py
or with pytest:
    ./virtenv/bin/python -m pytest tests/
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEG = os.path.join(ROOT, "custom_components", "stihl_connected")

# gatt.py imports bleak only for the connection itself; stub it so the decoders
# and read plans stay testable without the dependency.
_bleak = types.ModuleType("bleak")
_bleak.BleakClient = object
_backends = types.ModuleType("bleak.backends")
_device = types.ModuleType("bleak.backends.device")
_device.BLEDevice = object
sys.modules.setdefault("bleak", _bleak)
sys.modules.setdefault("bleak.backends", _backends)
sys.modules.setdefault("bleak.backends.device", _device)

_pkg = types.ModuleType("_stihl")
_pkg.__path__ = [INTEG]
sys.modules.setdefault("_stihl", _pkg)

_spec = importlib.util.spec_from_file_location(
    "_stihl.gatt", os.path.join(INTEG, "gatt.py")
)
gatt = importlib.util.module_from_spec(_spec)
sys.modules["_stihl.gatt"] = gatt
_spec.loader.exec_module(gatt)


def _plan(family: str) -> dict[str, str]:
    """{uuid: key} for a family's read plan."""
    return {uuid: key for uuid, key, _dec, _t in gatt._READS_BY_FAMILY[family]}


def _decoders(family: str) -> dict[str, object]:
    return {key: dec for _u, key, dec, _t in gatt._READS_BY_FAMILY[family]}


DIS = {
    "00002a24-0000-1000-8000-00805f9b34fb": "model_number",
    "00002a27-0000-1000-8000-00805f9b34fb": "hw_revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "sw_revision",
}


def test_bc2_connector_info_numbering():
    # ConnectorInfoServiceKt (bc2): ENV_TEMP is 0001, not 0002 — the BC2
    # variant has no coin-cell characteristic to occupy the first slot.
    plan = _plan("BC2")
    assert plan["e1800001-d696-449b-8516-9970e85e4148"] == "env_temperature"
    assert plan["e1800002-d696-449b-8516-9970e85e4148"] == "min_max_temp"
    assert plan["e1800003-d696-449b-8516-9970e85e4148"] == "device_unix_time"


def test_bc2_has_no_coin_cell_voltage():
    assert "coin_cell_voltage" not in _plan("BC2").values()


def test_bc2_battery_settings():
    plan = _plan("BC2")
    assert plan["4b188001-d250-49f0-9f7f-81e677279c39"] == "charge_mode"
    assert plan["4b188002-d250-49f0-9f7f-81e677279c39"] == "storage_charge_mode"
    assert plan["4b188003-d250-49f0-9f7f-81e677279c39"] == "silent_charge_window"


def test_sc2a_connector_info_numbering():
    plan = _plan("SC2A")
    assert plan["6cbb0001-3309-4730-982c-92a66e13bdc4"] == "coin_cell_voltage"
    assert plan["6cbb0002-3309-4730-982c-92a66e13bdc4"] == "env_temperature"
    assert plan["6cbb0003-3309-4730-982c-92a66e13bdc4"] == "min_max_temp"
    assert plan["6cbb0004-3309-4730-982c-92a66e13bdc4"] == "device_unix_time"
    assert plan["6cbb000a-3309-4730-982c-92a66e13bdc4"] == "linked_machine_serial"


def test_sc2a_machine_info_numbering():
    plan = _plan("SC2A")
    assert plan["8e580002-3b28-4145-9213-f0646c15ab5e"] == "last_seen_machine_serial"
    assert plan["8e580003-3b28-4145-9213-f0646c15ab5e"] == "battery_voltage_live"
    assert plan["8e580007-3b28-4145-9213-f0646c15ab5e"] == "linked_tool_id"
    assert plan["8e580008-3b28-4145-9213-f0646c15ab5e"] == "master_motor_runtime"
    assert plan["8e580009-3b28-4145-9213-f0646c15ab5e"] == "master_motor_speed"
    assert plan["8e58000b-3b28-4145-9213-f0646c15ab5e"] == "battery_current"
    assert plan["8e58000e-3b28-4145-9213-f0646c15ab5e"] == "battery_state_indicator"


def test_v72_machine_info_numbering():
    # v72/MachineInfoService: its own layout, one slot lower than the old
    # assumption from 000F upward, and the temperatures live at 0018/0019.
    plan = _plan("IC72V")
    assert plan["8e58000f-3b28-4145-9213-f0646c15ab5e"] == "master_input_current"
    assert plan["8e580010-3b28-4145-9213-f0646c15ab5e"] == "battery_voltage_high_side"
    assert plan["8e580011-3b28-4145-9213-f0646c15ab5e"] == "battery_voltage_low_side"
    assert plan["8e580014-3b28-4145-9213-f0646c15ab5e"] == "master_electronic_runtime"
    assert plan["8e580015-3b28-4145-9213-f0646c15ab5e"] == "master_motor_start_count"
    assert plan["8e580017-3b28-4145-9213-f0646c15ab5e"] == "master_electronic_start_count"
    assert plan["8e580018-3b28-4145-9213-f0646c15ab5e"] == "master_motor_temperature"
    assert plan["8e580019-3b28-4145-9213-f0646c15ab5e"] == "master_electronic_temperature"


def test_v72_omits_characteristics_it_does_not_have():
    # No BATTERY_VOLTAGE (0003), BATTERY_CURRENT (000B) or
    # BATTERY_STATE_INDICATOR (000E) in the v72 service.
    plan = _plan("IC72V")
    for absent in ("8e580003", "8e58000b", "8e58000e"):
        assert not any(u.startswith(absent) for u in plan), absent


def test_v72_temperatures_are_16_bit():
    dec = _decoders("IC72V")
    assert dec["master_motor_temperature"] is gatt._s16le
    assert dec["master_electronic_temperature"] is gatt._s16le


def test_v72_start_counts_are_16_bit():
    dec = _decoders("IC72V")
    assert dec["master_motor_start_count"] is gatt._u16le
    assert dec["master_electronic_start_count"] is gatt._u16le


def test_apx00_and_arx000_are_device_info_only():
    # Neither family has a connector class in the app, so ConnectorInfo does
    # not exist on them.
    assert _plan("APX00") == DIS
    assert _plan("ARX000") == DIS


def test_sc1_families_have_no_reads():
    assert gatt._READS_BY_FAMILY["SC1"] == []
    assert gatt._READS_BY_FAMILY["SC1MP"] == []


def test_connector_info_temperature_decoders():
    for family in ("BC2", "SC2A", "IC72V"):
        dec = _decoders(family)
        assert dec["env_temperature"] is gatt._temp_tenths
        assert dec["min_max_temp"] is gatt._min_max_temp


def test_temp_tenths():
    # 16-bit LE, tenths of a degree C. 0x00FF is the reading behind issue #1's
    # "13 V" coin-cell value, with a reference sensor at 23.4 C in the room.
    assert gatt._temp_tenths(bytes.fromhex("ff00")) == 25.5
    assert gatt._temp_tenths(bytes.fromhex("cd00")) == 20.5
    assert gatt._temp_tenths(bytes.fromhex("8600")) == 13.4
    assert gatt._temp_tenths(bytes.fromhex("0000")) == 0.0
    # signed, so a frosty morning reads negative instead of wrapping to ~6500 C
    assert gatt._temp_tenths(bytes.fromhex("f6ff")) == -1.0
    assert gatt._temp_tenths(b"\x01") is None


def test_min_max_temp():
    assert gatt._min_max_temp(bytes.fromhex("cd008600")) == (20.5, 13.4)
    assert gatt._min_max_temp(bytes.fromhex("9cffff00")) == (-10.0, 25.5)
    # 4 bytes required — the old sint8-pair decoder accepted 2 and was wrong
    assert gatt._min_max_temp(bytes.fromhex("cd00")) is None


def test_every_plan_entry_has_a_known_target():
    known = {"sensors", "booleans", "device_info", "_indicator_bits", "_min_max"}
    for family, plan in gatt._READS_BY_FAMILY.items():
        for _uuid, key, _dec, target in plan:
            assert target in known, f"{family}.{key} -> {target}"


def test_no_duplicate_uuids_within_a_plan():
    for family, plan in gatt._READS_BY_FAMILY.items():
        uuids = [u for u, _k, _d, _t in plan]
        assert len(uuids) == len(set(uuids)), family


def test_integer_decoders():
    assert gatt._u8(b"\xcd") == 205
    assert gatt._u8(b"") is None
    assert gatt._u16le(bytes.fromhex("cd00")) == 205
    assert gatt._u16le(b"\x01") is None
    assert gatt._s16le(bytes.fromhex("ffff")) == -1
    assert gatt._s16le(bytes.fromhex("d2fe")) == -302
    assert gatt._u32le(bytes.fromhex("b0410000")) == 16816
    assert gatt._u32le(bytes.fromhex("b04100")) is None


def test_ascii_decoder():
    assert gatt._ascii(b"4850\x00\x00") == "4850"
    assert gatt._ascii(b"  SW:01.02 ") == "SW:01.02"
    assert gatt._ascii(b"") is None
    assert gatt._ascii(b"\x00") is None


def test_charge_and_storage_modes():
    assert gatt._charge_mode(b"\x00") == "normal"
    assert gatt._charge_mode(b"\x02") == "rapid"
    assert gatt._charge_mode(b"\x09") == "unknown_9"
    assert gatt._storage_mode(b"\x00") == "off"
    assert gatt._storage_mode(b"\x01") == "active"


def test_silent_charge_window():
    assert gatt._sil_window(bytes([22, 30, 0, 6, 5, 0])) == "22:30-06:05"
    assert gatt._sil_window(bytes([22, 30, 0])) is None


def test_battery_state_indicator_bits():
    bits = gatt._decode_battery_state_indicator(b"\x41")
    assert bits["indicator_cold"] is True
    assert bits["indicator_temperature_alarm"] is True
    assert bits["indicator_warm"] is False
    assert gatt._decode_battery_state_indicator(b"") is None


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e!r}")
    sys.exit(1 if failed else 0)
