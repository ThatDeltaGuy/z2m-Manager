"""Switch platform for Zigbee2MQTT Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import signal_bridge_info
from .entity import Z2MBridgeEntity
from .hub import Z2MHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the permit-join switch."""
    hub = entry.runtime_data
    async_add_entities([Z2MPermitJoinSwitch(hub)])


class Z2MPermitJoinSwitch(Z2MBridgeEntity, SwitchEntity):
    """Allow new Zigbee devices to join the network."""

    _attr_translation_key = "permit_join"

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_permit_join"

    @property
    def is_on(self) -> bool:
        if self._hub.bridge_info is None:
            return False
        return self._hub.bridge_info.permit_join

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._hub.async_permit_join(self._hub.permit_join_duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._hub.async_permit_join(0)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_bridge_info(self._hub.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, _info: Any) -> None:
        self.async_write_ha_state()
