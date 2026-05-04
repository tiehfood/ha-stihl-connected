"""Active+passive Bluetooth coordinator for STIHL Connected.

Falls back to passive-only when no connectable BLE adapter / proxy is in
range. Otherwise, polls a curated set of GATT characteristics to enrich
the data already available from the advertisement.

Polling cadence (per HA core convention — see oralb, inkbird, etc.):
  - First contact with a connectable adapter → poll once.
  - Subsequently → poll only when the advertisement signals interesting
    state ("data sync overdue" or pending history) within URGENT_INTERVAL,
    otherwise no more often than MIN_INTERVAL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.components.bluetooth.active_update_processor import (
    ActiveBluetoothProcessorCoordinator,
)
from homeassistant.core import CoreState, HomeAssistant, callback

from .const import STIHL_MANUFACTURER_ID
from .gatt import read_all
from .parser import StihlAdvertisement, parse

_LOGGER = logging.getLogger(__name__)

# Minimum seconds between polls when nothing interesting has changed.
MIN_POLL_INTERVAL = 3600.0   # 1 h
# Faster cadence when the advertisement signals new data is buffered.
URGENT_POLL_INTERVAL = 300.0  # 5 min


@dataclass
class StihlData:
    """Merged result of advertisement decoding + (optional) GATT reads."""

    adv: StihlAdvertisement
    gatt_sensors: dict[str, Any] = field(default_factory=dict)
    gatt_booleans: dict[str, bool] = field(default_factory=dict)
    gatt_device_info: dict[str, str] = field(default_factory=dict)


def _decode(service_info: BluetoothServiceInfoBleak) -> StihlAdvertisement | None:
    mfg = service_info.manufacturer_data.get(STIHL_MANUFACTURER_ID)
    if not mfg:
        return None
    return parse(bytes(mfg))


class StihlActiveBluetoothProcessorCoordinator(
    ActiveBluetoothProcessorCoordinator[StihlData | None]
):
    """Coordinator that merges advertisement + GATT poll results.

    GATT polling is purely opportunistic: if the local adapter / proxy in
    range can establish an active connection, we do it. Otherwise we run
    in passive-only mode and only advertisement-derived sensors exist.
    """

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            address=address.upper(),
            mode=BluetoothScanningMode.PASSIVE,
            update_method=self._update_method,
            needs_poll_method=self._needs_poll,
            poll_method=self._poll,
            connectable=False,  # accept advertisements from passive sources too
        )
        self._gatt_sensors: dict[str, Any] = {}
        self._gatt_booleans: dict[str, bool] = {}
        self._gatt_device_info: dict[str, str] = {}
        self._first_poll_done = False

    # ------------------------------------------------------------------
    # Advertisement → StihlData merge
    # ------------------------------------------------------------------
    def _update_method(
        self, service_info: BluetoothServiceInfoBleak
    ) -> StihlData | None:
        adv = _decode(service_info)
        if adv is None:
            return None
        return StihlData(
            adv=adv,
            gatt_sensors=dict(self._gatt_sensors),
            gatt_booleans=dict(self._gatt_booleans),
            gatt_device_info=dict(self._gatt_device_info),
        )

    # ------------------------------------------------------------------
    # Whether to escalate to a connection
    # ------------------------------------------------------------------
    @callback
    def _needs_poll(
        self,
        service_info: BluetoothServiceInfoBleak,
        last_poll: float | None,
    ) -> bool:
        if self.hass.state is not CoreState.running:
            return False
        # Only poll if a CONNECTABLE adapter is in range. If there's only
        # a passive proxy (e.g. a passive Shelly), gracefully degrade.
        connectable_dev = async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if connectable_dev is None:
            return False
        adv = _decode(service_info)
        if adv is None:
            return False
        if last_poll is None:
            _LOGGER.debug(
                "%s: first connectable contact, running initial GATT poll "
                "(family=%s)", service_info.address, adv.family,
            )
            return True
        interesting = adv.booleans.get("data_sync_older_24h") or any(
            adv.booleans.get(k)
            for k in (
                "history_event_avail",
                "history_charge_avail",
                "history_discharge_avail",
                "history_standby_avail",
            )
        )
        threshold = URGENT_POLL_INTERVAL if interesting else MIN_POLL_INTERVAL
        return last_poll > threshold

    # ------------------------------------------------------------------
    # GATT fetch
    # ------------------------------------------------------------------
    async def _poll(
        self, service_info: BluetoothServiceInfoBleak
    ) -> StihlData | None:
        adv = _decode(service_info)
        if adv is None:
            return None
        device = async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if device is None:
            _LOGGER.debug(
                "%s: poll requested but no connectable adapter available",
                service_info.address,
            )
            return StihlData(
                adv=adv,
                gatt_sensors=dict(self._gatt_sensors),
                gatt_booleans=dict(self._gatt_booleans),
                gatt_device_info=dict(self._gatt_device_info),
            )
        try:
            sensors, booleans, device_info = await read_all(device, adv.family)
            self._gatt_sensors.update(sensors)
            self._gatt_booleans.update(booleans)
            self._gatt_device_info.update(device_info)
            self._first_poll_done = True
            _LOGGER.debug(
                "%s: GATT poll OK — %d sensors, %d binary, %d device-info",
                service_info.address,
                len(sensors), len(booleans), len(device_info),
            )
        except Exception as e:  # noqa: BLE001 — log and degrade
            _LOGGER.debug(
                "%s: GATT poll failed (%s: %s)",
                service_info.address, type(e).__name__, e,
            )
        return StihlData(
            adv=adv,
            gatt_sensors=dict(self._gatt_sensors),
            gatt_booleans=dict(self._gatt_booleans),
            gatt_device_info=dict(self._gatt_device_info),
        )
