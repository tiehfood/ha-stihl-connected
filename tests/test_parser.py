"""Unit tests for the STIHL advertisement parser.

Run from repo root:
    ./virtenv/bin/python tests/test_parser.py
or with pytest:
    ./virtenv/bin/python -m pytest tests/
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types

# Build a synthetic package "_stihl" that mirrors the integration's parser
# package, so we can import parser.py / const.py without pulling in the
# HA-dependent siblings (__init__.py, coordinator.py, ...).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEG = os.path.join(ROOT, "custom_components", "stihl_connected")

_pkg = types.ModuleType("_stihl")
_pkg.__path__ = [INTEG]
sys.modules.setdefault("_stihl", _pkg)


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(INTEG, filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


_const = _load("_stihl.const", "const.py")
_parser = _load("_stihl.parser", "parser.py")
parse = _parser.parse


PAYLOADS = {
    "ic72v_a": "08092bfd018c69fcf92b0000001f000000005601",
    "bc2_b":   "0605089ed038000c37b04100008e0ac900130201",  # SOC 19 SOH 95
    "bc2_c":   "0605109ed038000c34e02b00008e0a7600640201",  # SOC 100 SOH 92
}


def test_unknown_returns_none():
    assert parse(b"\x00" * 20) is None


def test_too_short():
    assert parse(b"\x06\x05") is None


def test_too_long():
    assert parse(bytes.fromhex(PAYLOADS["bc2_b"]) + b"\x00") is None


def test_bc2_b_decoding():
    a = parse(bytes.fromhex(PAYLOADS["bc2_b"]))
    assert a is not None
    assert a.family == "BC2"
    assert a.sensors["state_of_charge"] == 19
    assert a.sensors["state_of_health"] == 95
    assert a.sensors["operation_mode"] == "POWER_OFF"
    assert a.sensors["bms_thermal_state"] == "PERFECT"
    assert a.sensors["bms_hw_sw_error"] == "OK"
    assert a.sensors["bc_state"] == "WORKING_PROPERLY"
    assert a.sensors["tool_id"] == 0x00C9
    assert a.sensors["total_runtime"] == 0x000041B0
    assert a.sensors["state_of_health_category"] == "EXCELLENT"
    assert a.booleans["motor_running"] is False
    assert a.booleans["button_pressed_15s"] is False
    assert a.booleans["low_voltage"] is False
    assert a.booleans["security_linked"] is True
    assert a.booleans["data_sync_older_24h"] is True
    assert a.booleans["security_active"] is True
    assert a.sw_version == "1.02"


def test_bc2_c_decoding():
    a = parse(bytes.fromhex(PAYLOADS["bc2_c"]))
    assert a is not None
    assert a.family == "BC2"
    assert a.sensors["state_of_charge"] == 100
    assert a.sensors["state_of_health"] == 92
    assert a.sensors["state_of_health_category"] == "EXCELLENT"  # 92 in 90..100
    assert a.sensors["tool_id"] == 0x0076
    assert a.serial.isdigit() and len(a.serial) == 10


def test_soh_category_buckets():
    # Mirror StateOfHealthKt.asStateOfHealth boundaries: 100/90/89/75/74/60/59
    # We exercise by crafting payloads with controlled SOH bytes.
    base = bytes.fromhex("0605109ed038000c34e02b00008e0a7600640201")
    def with_soh(pct):
        soh_byte = pct - 40  # bytes 8 stores (SOH-40); test using exact pct
        b = bytearray(base)
        b[8] = soh_byte & 0x3F
        return bytes(b)
    for pct, expected in [(100, "EXCELLENT"), (90, "EXCELLENT"),
                          (89, "GOOD"), (75, "GOOD"),
                          (74, "MEDIUM"), (60, "MEDIUM"),
                          (59, "BAD"), (40, "BAD")]:
        a = parse(with_soh(pct))
        assert a is not None
        assert a.sensors["state_of_health"] == pct
        assert a.sensors["state_of_health_category"] == expected, (pct, expected, a.sensors["state_of_health_category"])


def test_ic72v_decoding():
    a = parse(bytes.fromhex(PAYLOADS["ic72v_a"]))
    assert a is not None
    assert a.family == "IC72V"
    assert a.sensors["motor_runtime"] == 0x00002BF9
    assert a.booleans["machine_linked"] is True
    assert a.booleans["security_active"] is True
    assert a.sw_version == "1.86"
    # IC72V's "serial" field is just the BLE MAC; show as MAC notation,
    # not the useless 15-digit decimal that getSerialnumber() yields.
    assert a.serial == "FC:69:8C:01:FD:2B"


def test_two_bc2_distinct_serials():
    a = parse(bytes.fromhex(PAYLOADS["bc2_b"]))
    b = parse(bytes.fromhex(PAYLOADS["bc2_c"]))
    assert a is not None and b is not None
    assert a.serial != b.serial


def test_serial_is_zero_padded_10_digits():
    # The parser keeps the 10-digit zero-padded form internally; the HA
    # integration's `display_serial` helper (entity.py) strips leading zeros
    # for the user-facing name — matching the official STIHL app.
    a = parse(bytes.fromhex(PAYLOADS["bc2_b"]))
    b = parse(bytes.fromhex(PAYLOADS["bc2_c"]))
    assert a is not None and b is not None
    assert len(a.serial) == 10 and a.serial.isdigit()
    assert len(b.serial) == 10 and b.serial.isdigit()


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
