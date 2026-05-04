"""Binary sensor platform for STIHL Connected."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import StihlActiveBluetoothProcessorCoordinator, StihlData
from .entity import make_device_info


# Curated descriptions for known binary sensor keys.
def _bd(key: str, *, name: str | None = None,
        category: EntityCategory | None = None,
        device_class: BinarySensorDeviceClass | None = None,
        icon: str | None = None,
        enabled_default: bool | None = None) -> BinarySensorEntityDescription:
    """Build a BinarySensorEntityDescription.

    Diagnostic entities are disabled by default unless `enabled_default=True`
    is passed explicitly. Non-diagnostic entities default to enabled.
    """
    if enabled_default is None:
        enabled_default = category != EntityCategory.DIAGNOSTIC
    return BinarySensorEntityDescription(
        key=key,
        translation_key=key,
        name=name,
        entity_category=category,
        device_class=device_class,
        icon=icon,
        entity_registry_enabled_default=enabled_default,
    )


BINARY_DESCRIPTIONS: dict[str, BinarySensorEntityDescription] = {
    "motor_running": _bd("motor_running", name="Motor Running",
                         device_class=BinarySensorDeviceClass.RUNNING),
    "button_pressed_15s": _bd("button_pressed_15s", name="Button Pressed (15s)",
                              icon="mdi:gesture-tap-button"),
    "low_voltage": _bd("low_voltage", name="Low Voltage",
                       device_class=BinarySensorDeviceClass.BATTERY),
    "hw_error": _bd("hw_error", name="Hardware Error",
                    device_class=BinarySensorDeviceClass.PROBLEM),
    "sw_error": _bd("sw_error", name="Software Error",
                    device_class=BinarySensorDeviceClass.PROBLEM),
    "is_connectable": _bd("is_connectable", name="Connectable",
                          category=EntityCategory.DIAGNOSTIC),
    "bms_com_error": _bd("bms_com_error", name="BMS Comms Error",
                         device_class=BinarySensorDeviceClass.PROBLEM),
    "com_issue": _bd("com_issue", name="Communication Issue",
                     device_class=BinarySensorDeviceClass.PROBLEM),
    "short_press_event": _bd("short_press_event", name="Short Press Event",
                             category=EntityCategory.DIAGNOSTIC),
    "security_active": _bd("security_active", name="Security Active",
                           category=EntityCategory.DIAGNOSTIC),
    "security_linked": _bd("security_linked", name="Security Linked",
                           category=EntityCategory.DIAGNOSTIC,
                           icon="mdi:link-variant"),
    "security_linking_requested": _bd("security_linking_requested",
                                      name="Security Linking Requested",
                                      category=EntityCategory.DIAGNOSTIC),
    "rtc_out_of_sync": _bd("rtc_out_of_sync", name="RTC Out of Sync",
                           category=EntityCategory.DIAGNOSTIC,
                           device_class=BinarySensorDeviceClass.PROBLEM),
    "data_sync_older_24h": _bd("data_sync_older_24h",
                               name="Data Sync Older Than 24h",
                               category=EntityCategory.DIAGNOSTIC),
    "history_event_avail": _bd("history_event_avail",
                               name="Event History Available",
                               category=EntityCategory.DIAGNOSTIC),
    "history_charge_avail": _bd("history_charge_avail",
                                name="Charge History Available",
                                category=EntityCategory.DIAGNOSTIC),
    "history_discharge_avail": _bd("history_discharge_avail",
                                   name="Discharge History Available",
                                   category=EntityCategory.DIAGNOSTIC),
    "history_standby_avail": _bd("history_standby_avail",
                                 name="Standby History Available",
                                 category=EntityCategory.DIAGNOSTIC),
    "reduced_feature_mode": _bd("reduced_feature_mode",
                                name="Reduced Feature Mode",
                                category=EntityCategory.DIAGNOSTIC),
    "reduced_feature_battery": _bd("reduced_feature_battery",
                                   name="Reduced Feature (Battery)",
                                   category=EntityCategory.DIAGNOSTIC),
    "reduced_feature_temperature": _bd("reduced_feature_temperature",
                                       name="Reduced Feature (Temperature)",
                                       category=EntityCategory.DIAGNOSTIC),
    "attached_to_other_machine": _bd("attached_to_other_machine",
                                     name="Attached to Other Machine",
                                     category=EntityCategory.DIAGNOSTIC),
    "coin_cell_error": _bd("coin_cell_error", name="Coin Cell Error",
                           device_class=BinarySensorDeviceClass.PROBLEM),
    "virtual_mark_set": _bd("virtual_mark_set", name="Virtual Mark Set",
                            category=EntityCategory.DIAGNOSTIC),
    "runtime_history_avail": _bd("runtime_history_avail",
                                 name="Runtime History Available",
                                 category=EntityCategory.DIAGNOSTIC),
    "event_history_avail": _bd("event_history_avail",
                               name="Event History Available",
                               category=EntityCategory.DIAGNOSTIC),
    "raw_data_avail": _bd("raw_data_avail", name="Raw Data Available",
                          category=EntityCategory.DIAGNOSTIC),
    "machine_linked": _bd("machine_linked", name="Machine Linked",
                          category=EntityCategory.DIAGNOSTIC),
    "machine_serial_avail": _bd("machine_serial_avail",
                                name="Machine Serial Available",
                                category=EntityCategory.DIAGNOSTIC),
    "message_available": _bd("message_available", name="Message Available"),
    "error_indication": _bd("error_indication", name="Error Indication",
                            device_class=BinarySensorDeviceClass.PROBLEM),
    "event_error": _bd("event_error", name="Event: Error",
                       device_class=BinarySensorDeviceClass.PROBLEM),
    "event_maintenance": _bd("event_maintenance", name="Event: Maintenance"),
    "event_usage": _bd("event_usage", name="Event: Usage",
                       category=EntityCategory.DIAGNOSTIC),
    "event_misc": _bd("event_misc", name="Event: Misc",
                      category=EntityCategory.DIAGNOSTIC),
    "event_silent": _bd("event_silent", name="Event: Silent",
                        category=EntityCategory.DIAGNOSTIC),
    "maintenance_due": _bd("maintenance_due", name="Maintenance Due",
                           device_class=BinarySensorDeviceClass.PROBLEM),
    "change_battery": _bd("change_battery", name="Change Battery",
                          device_class=BinarySensorDeviceClass.BATTERY),
    "error_notifier_active": _bd("error_notifier_active",
                                 name="Error Notifier Active",
                                 device_class=BinarySensorDeviceClass.PROBLEM),
    "data_avail": _bd("data_avail", name="Data Available",
                      category=EntityCategory.DIAGNOSTIC),
    "data_avail_in_storage": _bd("data_avail_in_storage", name="Data In Storage",
                                 category=EntityCategory.DIAGNOSTIC),
    "service_needed": _bd("service_needed", name="Service Needed",
                          device_class=BinarySensorDeviceClass.PROBLEM),
    "master_changed": _bd("master_changed", name="Master Changed",
                          category=EntityCategory.DIAGNOSTIC),
}


def _description_for(key: str) -> BinarySensorEntityDescription:
    if (desc := BINARY_DESCRIPTIONS.get(key)) is not None:
        return desc
    return BinarySensorEntityDescription(
        key=key,
        name=key.replace("_", " ").title(),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


def _make_converter(address: str):
    def _convert(parsed: StihlData | None) -> PassiveBluetoothDataUpdate[
        bool | None
    ]:
        if parsed is None:
            return PassiveBluetoothDataUpdate(
                devices={}, entity_descriptions={},
                entity_data={}, entity_names={},
            )
        descriptions: dict[PassiveBluetoothEntityKey, BinarySensorEntityDescription] = {}
        data: dict[PassiveBluetoothEntityKey, bool | None] = {}
        names: dict[PassiveBluetoothEntityKey, str | None] = {}
        merged = {**parsed.adv.booleans, **parsed.gatt_booleans}
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
            StihlBluetoothBinarySensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class StihlBluetoothBinarySensorEntity(
    PassiveBluetoothProcessorEntity[
        PassiveBluetoothDataProcessor[bool | None, Any]
    ],
    BinarySensorEntity,
):
    """A STIHL passive binary sensor."""

    @property
    def is_on(self) -> bool | None:
        return self.processor.entity_data.get(self.entity_key)

    @property
    def available(self) -> bool:
        return super().available and self.entity_key in self.processor.entity_data
