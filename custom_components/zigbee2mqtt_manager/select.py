"""Select platform for Zigbee2MQTT Manager."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import LOG_LEVELS, signal_bridge_info
from .entity import Z2MBridgeEntity
from .hub import Z2MHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the log level select."""
    hub = entry.runtime_data
    async_add_entities([Z2MLogLevelSelect(hub)])


class Z2MLogLevelSelect(Z2MBridgeEntity, SelectEntity):
    """Zigbee2MQTT's runtime log level."""

    _attr_translation_key = "log_level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = LOG_LEVELS

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_log_level"

    @property
    def current_option(self) -> str | None:
        if self._hub.bridge_info is None:
            return None
        return self._hub.bridge_info.log_level

    async def async_select_option(self, option: str) -> None:
        await self._hub.async_set_log_level(option)

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
