"""Binary sensor platform for Zigbee2MQTT Manager."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import signal_bridge_state
from .entity import Z2MBridgeEntity
from .hub import Z2MHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the bridge connectivity binary sensor."""
    hub = entry.runtime_data
    async_add_entities([Z2MBridgeConnectivitySensor(hub)])


class Z2MBridgeConnectivitySensor(Z2MBridgeEntity, BinarySensorEntity):
    """Whether the Zigbee2MQTT bridge is currently online."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "bridge_connectivity"

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_connectivity"

    @property
    def is_on(self) -> bool:
        return self._hub.bridge_online

    @property
    def available(self) -> bool:
        # This sensor's entire purpose is to report online/offline - it must
        # not itself go unavailable exactly when the bridge is offline.
        return True

    async def async_added_to_hass(self) -> None:
        # Deliberately not calling super().async_added_to_hass(): this entity
        # overrides `available` to not depend on bridge_online at all, so the
        # base class's availability-driven re-write subscription would be
        # redundant here. The subscription below already re-writes state
        # (for is_on) on every bridge/state change anyway.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_bridge_state(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _online: bool) -> None:
        self.async_write_ha_state()
