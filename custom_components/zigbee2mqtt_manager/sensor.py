"""Sensor platform for Zigbee2MQTT Manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorExtraStoredData,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import (
    signal_bridge_groups,
    signal_bridge_info,
    signal_device_metrics_changed,
    signal_networkmap,
    signal_offline_candidates_changed,
)
from .entity import Z2MBridgeEntity
from .hub import Z2MHub
from .models import NetworkMapResult


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up bridge-level sensors."""
    hub = entry.runtime_data
    async_add_entities(
        [
            Z2MBridgeInfoSensor(hub),
            Z2MNetworkMapSensor(hub),
            Z2MOfflineDevicesSensor(hub),
            Z2MBatteryLowDevicesSensor(hub),
            Z2MLowLqiDevicesSensor(hub),
            Z2MOtaAvailableDevicesSensor(hub),
        ]
    )


class Z2MBridgeInfoSensor(Z2MBridgeEntity, SensorEntity):
    """Zigbee2MQTT bridge version, network info, and configured groups."""

    _attr_translation_key = "bridge_info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_bridge_info"

    @property
    def native_value(self) -> str | None:
        if self._hub.bridge_info is None:
            return None
        return self._hub.bridge_info.version

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # bridge/info and bridge/groups arrive independently - groups must
        # stay populated even before the first bridge/info message lands.
        attributes: dict[str, Any] = {
            "groups": [group.friendly_name for group in self._hub.groups.values()],
        }
        info = self._hub.bridge_info
        if info is not None:
            attributes.update(
                {
                    "coordinator": info.coordinator,
                    "channel": info.network.get("channel"),
                    "pan_id": info.network.get("pan_id"),
                    "log_level": info.log_level,
                    "permit_join": info.permit_join,
                    "permit_join_end": info.permit_join_end,
                }
            )
        return attributes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_bridge_info(self._hub.entry_id),
                self._handle_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_bridge_groups(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _data: Any) -> None:
        self.async_write_ha_state()


@dataclass
class NetworkMapExtraStoredData(SensorExtraStoredData):
    """Extra data restored for the network map sensor across HA restarts.

    SensorExtraStoredData itself only restores native_value/unit - type and
    value need their own as_dict/from_dict round-trip so the sensor doesn't
    show a stale timestamp next to empty attributes after a restart.
    """

    networkmap_type: str
    value: Any

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "networkmap_type": self.networkmap_type, "value": self.value}

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> NetworkMapExtraStoredData | None:
        sensor_data = SensorExtraStoredData.from_dict(restored)
        if sensor_data is None or "networkmap_type" not in restored:
            return None
        return cls(
            native_value=sensor_data.native_value,
            native_unit_of_measurement=sensor_data.native_unit_of_measurement,
            networkmap_type=restored["networkmap_type"],
            value=restored.get("value"),
        )


class Z2MNetworkMapSensor(Z2MBridgeEntity, RestoreSensor):
    """Timestamp of the last network map refresh; the map itself is an attribute.

    Mirrors the structure of the MQTT-template sensor this replaces
    (state_topic -> timestamp, json_attributes_topic -> parsed value), as
    native code fed by the hub instead of a YAML template.
    """

    _attr_translation_key = "networkmap"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_networkmap"

    @property
    def native_value(self) -> datetime | None:
        result = self._hub.last_networkmap
        return result.refreshed_at if result is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self._hub.last_networkmap
        if result is None:
            return {}
        return {"type": result.type, "value": result.value}

    @property
    def extra_restore_state_data(self) -> NetworkMapExtraStoredData | None:
        result = self._hub.last_networkmap
        if result is None:
            return None
        return NetworkMapExtraStoredData(
            native_value=result.refreshed_at,
            native_unit_of_measurement=None,
            networkmap_type=result.type,
            value=result.value,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self._hub.last_networkmap is None:
            restored = await self.async_get_last_sensor_data()
            extra = await self.async_get_last_extra_data()
            if restored is not None and extra is not None:
                restored_extra = NetworkMapExtraStoredData.from_dict(extra.as_dict())
                if restored_extra is not None and restored.native_value is not None:
                    self._hub.last_networkmap = NetworkMapResult(
                        refreshed_at=restored.native_value,
                        type=restored_extra.networkmap_type,
                        value=restored_extra.value,
                    )

        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal_networkmap(self._hub.entry_id), self._handle_update)
        )

    @callback
    def _handle_update(self, _result: NetworkMapResult) -> None:
        self.async_write_ha_state()


class Z2MOfflineDevicesSensor(Z2MBridgeEntity, SensorEntity):
    """Count and list of Zigbee devices that look offline.

    Detection is per-device and auto-switching (see Z2MHub.compute_offline_devices):
    devices that publish an /availability topic are trusted exclusively via
    that signal, others fall back to a last_seen threshold. A device with
    neither signal is correctly omitted rather than guessed at.
    """

    _attr_translation_key = "offline_devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_offline_devices"

    @property
    def native_value(self) -> int:
        return len(self._hub.compute_offline_devices())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": device.friendly_name, "last_seen": device.since.isoformat()}
                for device in self._hub.compute_offline_devices()
            ]
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_offline_candidates_changed(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _data: Any) -> None:
        self.async_write_ha_state()


class Z2MBatteryLowDevicesSensor(Z2MBridgeEntity, SensorEntity):
    """Count and list of devices (excluding the coordinator) at or below the
    configured battery threshold.
    """

    _attr_translation_key = "battery_low_devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_battery_low_devices"

    @property
    def native_value(self) -> int:
        return len(self._hub.compute_battery_low_devices())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": device.friendly_name, "battery": device.battery}
                for device in self._hub.compute_battery_low_devices()
            ]
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_metrics_changed(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _data: Any) -> None:
        self.async_write_ha_state()


class Z2MLowLqiDevicesSensor(Z2MBridgeEntity, SensorEntity):
    """Count and list of devices (excluding the coordinator) at or below the
    configured link-quality threshold.
    """

    _attr_translation_key = "low_lqi_devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_low_lqi_devices"

    @property
    def native_value(self) -> int:
        return len(self._hub.compute_low_lqi_devices())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": device.friendly_name, "linkquality": device.linkquality}
                for device in self._hub.compute_low_lqi_devices()
            ]
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_metrics_changed(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _data: Any) -> None:
        self.async_write_ha_state()


class Z2MOtaAvailableDevicesSensor(Z2MBridgeEntity, SensorEntity):
    """Count and list of devices with a firmware update currently available.

    Unlike the battery/LQI sensors, the coordinator is not excluded here -
    some Zigbee adapters do support Zigbee2MQTT-managed firmware updates.
    """

    _attr_translation_key = "ota_available_devices"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_ota_available_devices"

    @property
    def native_value(self) -> int:
        return len(self._hub.compute_ota_available_devices())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "devices": [
                {"name": device.friendly_name} for device in self._hub.compute_ota_available_devices()
            ]
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_metrics_changed(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _data: Any) -> None:
        self.async_write_ha_state()
