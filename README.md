<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=tiehfood&repository=ha-stihl-connected&category=integration">
    <img alt="Open in HACS" src="https://my.home-assistant.io/badges/hacs_repository.svg"/>
  </a>
</p>
<p align="center">
  <a href="https://github.com/tiehfood/ha-stihl-connected/releases/latest">
    <img alt="Latest release" src="https://img.shields.io/github/v/release/tiehfood/ha-stihl-connected?label=release"/>
  </a>
  <a href="https://www.home-assistant.io">
    <img alt="HA 2024.12+" src="https://img.shields.io/badge/HA-2024.12%2B-blue.svg"/>
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/tiehfood/ha-stihl-connected.svg"/>
  </a>
  <a href="https://www.buymeacoffee.com/tiehfood">
    <img alt="Buy Me A Coffee" src="https://raw.githubusercontent.com/pachadotdev/buymeacoffee-badges/main/bmc-orange.svg"/>
  </a>
</p>

# STIHL Connected

Local Bluetooth integration for STIHL Connected hardware — AP smart batteries, AL chargers, Smart Connectors, IC72V mowers. Reads live data straight from the device. No cloud account, no app, no backend.

- Talks BLE directly to the device — works whenever an HA Bluetooth adapter or proxy is in range
- Decodes the 20-byte STIHL advertisement (manufacturer ID `0x03DD`) — sensors update every few seconds
- Pulls extra data over GATT when a connectable adapter is around: model, lifetime temps, charge mode, mower serial, live current, motor temperature
- Supports 7 device families (BC2, APX00, ARX000, SC2A, SC1, SC1MP, IC72V) — see table below
- Auto-discovers via HA's Bluetooth integration; one config-flow click adds the device
- Read-only by design — no writes, no pairing, no STIHL account needed

## Supported devices

| Family   | Examples                              | Passive sensors | Active GATT |
|----------|---------------------------------------|-----------------|-------------|
| **BC2**  | AP200S, AP500S, AP600S, ARxL          | SoC, SoH, BMS state, op mode, motor running, button press, low voltage, total runtime, last tool ID, security flags | coin-cell V, ambient/min/max temp, charge mode, storage charge, silent-charge schedule, model, HW/SW |
| **APX00** | older AP smart batteries              | SoH, op mode, voltage, temperature, LED state | (same as BC2) |
| **ARX000** | AL chargers, MP1                     | voltage, temperature, LED pattern, tool ID | (same as BC2) |
| **SC2A** | Smart Connector 2 A                   | status / event flags, signal indicators | linked machine serial, live battery V/I, motor RPM/runtime, battery state |
| **SC1**  | Smart Connector 1                     | voltage, temperature, status flags | DeviceInfo strings |
| **SC1MP** | Smart Connector 1.1                   | voltage, temperature, motor runtime | DeviceInfo strings |
| **IC72V** | RMA mower built-in connectors         | motor runtime, status flags | mower serial, dual-battery voltage, motor + inverter temp, RPM, start counts |

Diagnostic entities are created but disabled by default — enable them per device under **Configure entities**.

## Installation

### HACS

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tiehfood&repository=ha-stihl-connected&category=integration)

Or manually: HACS → ⋮ → Custom repositories → add `https://github.com/tiehfood/ha-stihl-connected` as **Integration** → install → restart HA.

### Manual

Copy `custom_components/stihl_connected/` into your HA config (final path: `<config>/custom_components/stihl_connected/`) and restart.

### Adding a device

Wake one of your STIHL devices near an HA Bluetooth source. A discovery card appears under **Settings → Devices & services**. If not, go to **Add Integration → STIHL Connected** — every previously-seen STIHL device shows up in the dropdown.

## Bluetooth source

You need at least one of these in range of the device:

- USB Bluetooth dongle on the HA host
- ESP32 running ESPHome with `bluetooth_proxy: { active: true }`
- Shelly Gen 2+ with the Bluetooth scanner enabled (active mode for GATT, passive is enough for advertisements)

Active GATT readouts need **at least one *connectable* adapter** within ~5 m of the device. Without one the integration falls back to passive-only sensors silently — no user toggle.

## Limitations

- **Read-only.** No LED beacon, charge-mode change, factory reset or firmware update. Writes require a per-device ECDSA-P256 keypair that the official app provisions through the STIHL cloud.
- **No charge cycle count.** That value lives only in STIHL's cloud, not in any BLE characteristic.
- **No history sync.** The HistoryDataStorage / HistogramDataStorage GATT services exist on the hardware but aren't exposed as service calls here.

## Troubleshooting

**Only some sensors show up?** Active GATT needs a connectable adapter in range. Check **Settings → Devices & services → Bluetooth → Configure** — your STIHL MAC must appear under *Connectable* for at least one scanner. If it's only under *Non-connectable*, move a proxy closer or switch its scanner to active.

**Names show as `STIHL Battery 953196048`?** Browser cache. Hard-reload the HA tab.

**Want debug logs?**

```yaml
logger:
  logs:
    custom_components.stihl_connected: debug
```

## Development

```sh
git clone https://github.com/tiehfood/ha-stihl-connected
cd ha-stihl-connected
python3 -m venv venv && . venv/bin/activate
python tests/test_parser.py
```

The parser has no HA imports, so tests run on plain Python.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is independent and not affiliated with, endorsed by, or supported by ANDREAS STIHL AG & Co. KG. STIHL® and the product names listed (BC2, APX, ARX, IC72V, AP, AL, MP1, AR, RMA, Smart Connector) are trademarks of ANDREAS STIHL AG & Co. KG and are used here for identification only.

The brand icon at `custom_components/stihl_connected/brand/` is the property of ANDREAS STIHL AG & Co. KG and is bundled here so Home Assistant can render the manufacturer logo on the device card. If a STIHL representative would like it removed or replaced, open an issue.
