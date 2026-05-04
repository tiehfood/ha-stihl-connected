"""Sensor platform for STIHL Connected."""
from __future__ import annotations

from typing import Any

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import StihlActiveBluetoothProcessorCoordinator, StihlData
from .entity import make_device_info


# Curated EntityDescriptions for known sensor keys (advertisement + GATT).
# Anything else falls back to a generic diagnostic SensorEntityDescription.
SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    # ---- advertisement-derived ----
    "state_of_charge": SensorEntityDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        name="State of Charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "state_of_health": SensorEntityDescription(
        key="state_of_health",
        translation_key="state_of_health",
        name="State of Health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-heart-variant",
    ),
    "voltage": SensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "operation_mode": SensorEntityDescription(
        key="operation_mode",
        translation_key="operation_mode",
        name="Operation Mode",
        device_class=SensorDeviceClass.ENUM,
        options=["power_off", "stand_by", "charging", "discharging"],
        icon="mdi:power-settings",
    ),
    "bms_thermal_state": SensorEntityDescription(
        key="bms_thermal_state",
        translation_key="bms_thermal_state",
        name="BMS Thermal State",
        device_class=SensorDeviceClass.ENUM,
        options=["frozen_alarm", "frozen", "cold", "perfect", "hot", "hot_alarm",
                 "fatal_error", "rfu_7"],
        icon="mdi:thermometer",
    ),
    "bms_hw_sw_error": SensorEntityDescription(
        key="bms_hw_sw_error",
        translation_key="bms_hw_sw_error",
        name="BMS HW/SW Error",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "factory_reset_done", "ext_flash_not_avail", "rfu"],
    ),
    "bc_state": SensorEntityDescription(
        key="bc_state",
        translation_key="bc_state",
        name="Battery Connector State",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=["working_properly", "rfu_01", "rfu_10", "rfu_11"],
    ),
    "tool_id": SensorEntityDescription(
        key="tool_id",
        translation_key="tool_id",
        name="Last Tool ID",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:wrench",
    ),
    "total_runtime": SensorEntityDescription(
        key="total_runtime",
        translation_key="total_runtime",
        name="Total Runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:timer-outline",
    ),
    "motor_runtime": SensorEntityDescription(
        key="motor_runtime",
        translation_key="motor_runtime",
        name="Motor Runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:engine",
    ),
    "state_of_health_category": SensorEntityDescription(
        key="state_of_health_category",
        translation_key="state_of_health_category",
        name="Battery Condition",
        device_class=SensorDeviceClass.ENUM,
        options=["excellent", "good", "medium", "bad"],
        icon="mdi:heart-pulse",
    ),
    "tx_power": SensorEntityDescription(
        key="tx_power",
        translation_key="tx_power",
        name="TX Power",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "led": SensorEntityDescription(
        key="led",
        translation_key="led",
        name="LED Pattern",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:led-on",
    ),
    "debug": SensorEntityDescription(
        key="debug",
        translation_key="debug",
        name="Debug",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "counter": SensorEntityDescription(
        key="counter",
        translation_key="counter",
        name="Counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
    ),

    # ---- GATT-derived (only present when active connection succeeded) ----
    "coin_cell_voltage": SensorEntityDescription(
        key="coin_cell_voltage",
        translation_key="coin_cell_voltage",
        name="Coin Cell Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "env_temperature": SensorEntityDescription(
        key="env_temperature",
        translation_key="env_temperature",
        name="Ambient Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "min_temperature_seen": SensorEntityDescription(
        key="min_temperature_seen",
        translation_key="min_temperature_seen",
        name="Minimum Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:thermometer-low",
    ),
    "max_temperature_seen": SensorEntityDescription(
        key="max_temperature_seen",
        translation_key="max_temperature_seen",
        name="Maximum Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:thermometer-high",
    ),
    "device_unix_time": SensorEntityDescription(
        key="device_unix_time",
        translation_key="device_unix_time",
        name="Device Clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:clock-outline",
    ),
    "charge_mode": SensorEntityDescription(
        key="charge_mode",
        translation_key="charge_mode",
        name="Charge Mode",
        device_class=SensorDeviceClass.ENUM,
        options=["normal", "rapid"],
        icon="mdi:battery-charging",
    ),
    "storage_charge_mode": SensorEntityDescription(
        key="storage_charge_mode",
        translation_key="storage_charge_mode",
        name="Storage Charge Mode",
        device_class=SensorDeviceClass.ENUM,
        options=["off", "active"],
        icon="mdi:battery-alert",
    ),
    "silent_charge_window": SensorEntityDescription(
        key="silent_charge_window",
        translation_key="silent_charge_window",
        name="Silent Charge Window",
        icon="mdi:volume-off",
    ),
    "linked_machine_serial": SensorEntityDescription(
        key="linked_machine_serial",
        translation_key="linked_machine_serial",
        name="Machine Serial",
        icon="mdi:identifier",
    ),
    "last_seen_machine_serial": SensorEntityDescription(
        key="last_seen_machine_serial",
        translation_key="last_seen_machine_serial",
        name="Last Seen Machine Serial",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:identifier",
    ),
    "battery_voltage_live": SensorEntityDescription(
        key="battery_voltage_live",
        translation_key="battery_voltage_live",
        name="Battery Voltage (live)",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_current": SensorEntityDescription(
        key="battery_current",
        translation_key="battery_current",
        name="Battery Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "linked_tool_id": SensorEntityDescription(
        key="linked_tool_id",
        translation_key="linked_tool_id",
        name="Linked Tool ID",
        icon="mdi:wrench-outline",
    ),
    "master_motor_runtime": SensorEntityDescription(
        key="master_motor_runtime",
        translation_key="master_motor_runtime",
        name="Master Motor Runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:engine",
    ),
    "master_motor_speed": SensorEntityDescription(
        key="master_motor_speed",
        translation_key="master_motor_speed",
        name="Master Motor Speed",
        native_unit_of_measurement="rpm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
    ),
    "battery_voltage_high_side": SensorEntityDescription(
        key="battery_voltage_high_side",
        translation_key="battery_voltage_high_side",
        name="Battery Voltage (high side)",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery_voltage_low_side": SensorEntityDescription(
        key="battery_voltage_low_side",
        translation_key="battery_voltage_low_side",
        name="Battery Voltage (low side)",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "master_input_current": SensorEntityDescription(
        key="master_input_current",
        translation_key="master_input_current",
        name="Master Input Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "master_motor_temperature": SensorEntityDescription(
        key="master_motor_temperature",
        translation_key="master_motor_temperature",
        name="Drive Motor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "master_electronic_temperature": SensorEntityDescription(
        key="master_electronic_temperature",
        translation_key="master_electronic_temperature",
        name="Inverter Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "master_motor_start_count": SensorEntityDescription(
        key="master_motor_start_count",
        translation_key="master_motor_start_count",
        name="Motor Start Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "master_electronic_runtime": SensorEntityDescription(
        key="master_electronic_runtime",
        translation_key="master_electronic_runtime",
        name="Electronic Runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    "master_electronic_start_count": SensorEntityDescription(
        key="master_electronic_start_count",
        translation_key="master_electronic_start_count",
        name="Electronic Start Count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


def _description_for(key: str) -> SensorEntityDescription:
    if (desc := SENSOR_DESCRIPTIONS.get(key)) is not None:
        return desc
    return SensorEntityDescription(
        key=key,
        name=key.replace("_", " ").title(),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def _make_converter(address: str):
    def _convert(parsed: StihlData | None) -> PassiveBluetoothDataUpdate[
        float | int | str | None
    ]:
        if parsed is None:
            return PassiveBluetoothDataUpdate(
                devices={}, entity_descriptions={},
                entity_data={}, entity_names={},
            )
        descriptions: dict[PassiveBluetoothEntityKey, SensorEntityDescription] = {}
        data: dict[PassiveBluetoothEntityKey, float | int | str | None] = {}
        names: dict[PassiveBluetoothEntityKey, str | None] = {}
        merged = {**parsed.adv.sensors, **parsed.gatt_sensors}
        for key, value in merged.items():
            ek = PassiveBluetoothEntityKey(key=key, device_id=None)
            desc = _description_for(key)
            descriptions[ek] = desc
            data[ek] = value
            names[ek] = desc.name
        return PassiveBluetoothDataUpdate(
            devices={None: make_device_info(parsed.adv, address, parsed.gatt_device_info)},
            entity_descriptions=descriptions,
            entity_data=data,
            entity_names=names,
        )
    return _convert


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: StihlActiveBluetoothProcessorCoordinator = (
        hass.data[DOMAIN][entry.entry_id]
    )
    processor = PassiveBluetoothDataProcessor(_make_converter(coordinator.address))
    entry.async_on_unload(
        processor.async_add_entities_listener(
            StihlBluetoothSensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class StihlBluetoothSensorEntity(
    PassiveBluetoothProcessorEntity[
        PassiveBluetoothDataProcessor[float | int | str | None, Any]
    ],
    SensorEntity,
):
    """A STIHL passive sensor entity."""

    @property
    def native_value(self) -> Any:
        return self.processor.entity_data.get(self.entity_key)

    @property
    def available(self) -> bool:
        return super().available and self.entity_key in self.processor.entity_data
