<p align="center">
  <a href="https://hacs.xyz">
    <img alt="HACS badge" src="https://img.shields.io/badge/HACS-Custom-orange.svg"/>
  </a>
  <a href="https://www.home-assistant.io">
    <img alt="HomeAssistant" src="https://img.shields.io/badge/HA-2024.12%2B-blue.svg"/>
  </a>
  <a href="LICENSE">
    <img alt="License" src="https://img.shields.io/github/license/tiehfood/ha-stihl-connected.svg"/>
  </a>
  <a href="https://github.com/tiehfood/ha-stihl-connected">
    <img alt="Stars" src="https://img.shields.io/github/stars/tiehfood/ha-stihl-connected?style=flat&label=github+stars"/>
  </a>
  <a href="https://www.buymeacoffee.com/tiehfood">
    <img alt="ByMeACoffee" src="https://raw.githubusercontent.com/pachadotdev/buymeacoffee-badges/main/bmc-orange.svg"/>
  </a>
</p>

# STIHL Connected — Home Assistant integration

Read live data from STIHL Connected hardware (AP batteries, Smart Connectors,
chargers, IC72V mowers etc.) directly over Bluetooth Low Energy. No STIHL
Cloud account, no app, no backend — everything runs locally in your Home
Assistant.

---

## Supported devices

The advertisement decoder recognises these device families:

| Family   | Examples                              | Sensors (passive)                            | Extra (active GATT)                  |
|----------|---------------------------------------|----------------------------------------------|--------------------------------------|
| **BC2**  | AP200S, AP500S, AP600S, ARxL          | SoC %, SoH %, BMS state, op mode, motor running, button press, low voltage, total runtime, last tool ID, security flags … | coin-cell V, env temp, lifetime min/max temp, charge mode, storage charge mode, silent-charge schedule, model/HW/SW strings |
| **APX00** | older AP smart batteries              | SoH %, op mode, voltage, temperature, LED state | (same as BC2 set)                    |
| **ARX000** | AL chargers, MP1                     | voltage, temperature, LED pattern, tool ID   | (same as BC2 set)                    |
| **SC2A** | Smart Connector 2 A                   | many status / event flags, signal indicators  | linked machine serial, live battery V/I, motor RPM, motor runtime, battery state indicator |
| **SC1**  | Smart Connector 1                     | voltage, temperature, status flags           | DeviceInfo strings                   |
| **SC1MP** | Smart Connector 1.1                   | voltage, temperature, motor runtime          | DeviceInfo strings                   |
| **IC72V** | mower built-in connectors (RMA 7 RV…) | motor runtime, status flags                  | mower serial, dual-battery voltage, motor + inverter temperature, motor RPM, motor / electronic start counts |

Diagnostic entities are created in the registry but disabled by default —
enable per-device under **Configure entities** if needed.

---

## How it works

```
   STIHL device          BLE proxy               Home Assistant
   -------------         -----------             ---------------
   advertisement   ▶▶▶   passive scan    ▶▶▶    PassiveBluetoothDataUpdate
                                                ↓
                                                 sensor / binary_sensor
   GATT connect    ▶▶▶   active scan     ▶▶▶    ActiveBluetoothProcessor
                                                ↓
                                                 extra sensors
                                                 (mower serial, live V/A, …)
```

- **Passive** mode (default): just listens to the 20-byte STIHL manufacturer-data
  block (company ID `0x03DD`, service UUID `0xFE43`). Always works.
- **Active** mode (opt-in by capability): if a connectable BLE adapter / proxy
  is in range, the integration also opens a GATT connection every 60 minutes
  (or every 5 minutes when a "data sync overdue" flag is set) and reads the
  read-only characteristics. **No authentication needed for reads.**
- If no connectable adapter is in range, active polling is skipped silently
  and only the passive sensors are present. No user toggle — the integration
  adapts automatically.

---

## Requirements

- **Home Assistant 2024.12** or newer (2026.3+ to render the bundled brand
  icon locally; older HAs show a generic placeholder until the brand is
  served from CDN)
- A **Bluetooth source** that reaches your STIHL hardware:
  - **Shelly Gen 2+** with the Bluetooth scanner option enabled in the
    official Shelly integration (set to **Active** for GATT — **Passive** is
    fine for advertisements only)
  - **ESPHome** ESP32 with `bluetooth_proxy: { active: true }`
  - or a USB Bluetooth dongle on the HA host

The integration installs `bleak-retry-connector>=3.5.0` via HA's standard
`requirements` mechanism. No other dependencies.

---

## Installation

### Via HACS (recommended)

1. **HACS → Integrations → ⋮ → Custom repositories**.
2. Add this repo's URL with category **Integration**.
3. Install **STIHL Connected**.
4. Restart Home Assistant.

### Manual

Copy `custom_components/stihl_connected/` into your HA config so the final
path is `<HA config>/custom_components/stihl_connected/`. Restart HA.

### Add devices

After restart, wake one of your STIHL devices near a Bluetooth proxy / your
HA host. **Settings → Devices & services** will show a discovery card —
click **Add**. Each STIHL device becomes one HA device with all its sensors.

If discovery doesn't trigger automatically:

- **Settings → Devices & services → Add integration → STIHL Connected** lists
  all already-seen-but-unconfigured STIHL devices in a dropdown.

---

## What this integration **doesn't** do

- **No writes** (LED beacon, charge mode change, factory reset, firmware
  update). Those require a device-paired ECDSA-P256 keypair the official
  app provisions through the STIHL Cloud — out of scope.
- **No charge cycles ("Ladezyklen")**. That number lives only in the cloud
  backend, not in any BLE characteristic.
- **No history sync**. The HistoryDataStorage and HistogramDataStorage GATT
  services exist and are documented in the protocol reference but not yet
  implemented as service calls in this integration.

---

## Troubleshooting

### "I see only some sensors / no GATT data"

Active GATT polling needs **at least one connectable adapter in range** of
the device. Verify under **Settings → Devices & services → Bluetooth →
Configure**: each scanner shows two lists — devices it can connect to vs
devices it can only see passively. For active GATT to work, your STIHL MAC
must appear under **Connectable** for at least one scanner.

If only Non-connectable: physically move the active proxy closer (≤5 m
through walls is realistic), or ensure proxies are in **active** scanner
mode (Shelly defaults to passive; ESPHome `bluetooth_proxy:` defaults to
passive unless `active: true` is set).

### Naming displays as "STIHL Battery 953196048"

If sensor names show only the device serial (no friendly label), hard-reload
the browser tab — HA caches integration translations aggressively.

### Enable debug logs

```yaml
logger:
  logs:
    custom_components.stihl_connected: debug
```

Restart, then the coordinator will log every poll attempt / skip / failure.


---

## Development

```sh
git clone <this-repo>
cd ha_stihl_connected
python3 -m venv venv && . venv/bin/activate
python tests/test_parser.py     # 9/9 passing
```

The parser is pure-python and has no HA dependencies, so the unit tests run
without HA installed.

For UI testing, copy `custom_components/stihl_connected/` into a HA dev
container, edit, restart.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Trademarks & assets

**STIHL**, the STIHL logo, and product names (BC2, APX, ARX, IC72V, AP, AL,
MP1, AR, RMA, Smart Connector, etc.) are trademarks of **ANDREAS STIHL AG &
Co. KG**.

The brand icon shipped under `custom_components/stihl_connected/brand/`
(and any other STIHL-branded imagery) is the property of ANDREAS STIHL AG
& Co. KG. It is bundled here only so Home Assistant can display the
manufacturer logo on the device card; no ownership or license to the mark
is claimed or transferred. If you are a STIHL representative and want the
icon removed or replaced, open an issue and it will be taken out.

This project is an independent, community-maintained integration. It is
**not affiliated with, endorsed by, or supported by** ANDREAS STIHL AG &
Co. KG. All product names, logos, and brands are property of their
respective owners and are used here for identification purposes only.