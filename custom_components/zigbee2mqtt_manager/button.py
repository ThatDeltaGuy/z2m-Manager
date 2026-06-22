"""Button platform for Zigbee2MQTT Manager.

Restart and the network-map refresh are bridge-level; remove/re-interview
are per-device, created only for devices device_link.py has resolved an
existing HA device for (see hub.py's link reconciliation).
"""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import signal_device_linkable
from .entity import Z2MBridgeEntity, Z2MLinkedDeviceEntity
from .hub import Z2MHub
from .models import DeviceLinkedPayload


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up bridge-level buttons, plus per-device buttons as devices link."""
    hub = entry.runtime_data
    async_add_entities([Z2MRestartButton(hub), Z2MNetworkMapRefreshButton(hub)])

    @callback
    def _async_device_linkable(payload: DeviceLinkedPayload) -> None:
        async_add_entities(
            [
                Z2MRemoveDeviceButton(hub, payload.ieee_address, payload.ha_device_id),
                Z2MReinterviewDeviceButton(hub, payload.ieee_address, payload.ha_device_id),
            ]
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_device_linkable(hub.entry_id), _async_device_linkable)
    )

    already_linked = [
        (ieee_address, link.ha_device_id)
        for ieee_address, link in hub._link_cache.items()
        if link.ha_device_id is not None
    ]
    async_add_entities(
        entity
        for ieee_address, ha_device_id in already_linked
        for entity in (
            Z2MRemoveDeviceButton(hub, ieee_address, ha_device_id),
            Z2MReinterviewDeviceButton(hub, ieee_address, ha_device_id),
        )
    )


class Z2MRestartButton(Z2MBridgeEntity, ButtonEntity):
    """Restart the Zigbee2MQTT instance.

    No async_added_to_hass override is needed: a button has no displayed
    state besides availability, and the base class already re-publishes on
    bridge online/offline changes.
    """

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_translation_key = "restart"

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_restart"

    async def async_press(self) -> None:
        await self._hub.async_restart()


class Z2MNetworkMapRefreshButton(Z2MBridgeEntity, ButtonEntity):
    """Trigger an on-demand network map refresh.

    Unlike the periodic refresh (which swallows failures - see
    Z2MHub._async_periodic_networkmap_refresh), a manual press should
    surface a failure to the user, so async_press lets it propagate.
    """

    _attr_translation_key = "refresh_networkmap"

    def __init__(self, hub: Z2MHub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.entry_id}_refresh_networkmap"

    async def async_press(self) -> None:
        await self._hub.async_refresh_networkmap()


class Z2MRemoveDeviceButton(Z2MLinkedDeviceEntity, ButtonEntity):
    """Remove a Zigbee device from the network.

    Deliberately soft-remove only (force=False) - force-remove is
    destructive/last-resort and only reachable via the remove_device
    service, to avoid a misclick on a dashboard button bricking a device's
    pairing state irrecoverably.
    """

    _attr_translation_key = "remove_device"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub: Z2MHub, ieee_address: str, ha_device_id: str) -> None:
        super().__init__(hub, ieee_address, ha_device_id)
        self._attr_unique_id = f"{hub.entry_id}_{ieee_address}_remove"

    async def async_press(self) -> None:
        await self._hub.async_remove_device(self._ieee_address, force=False)


class Z2MReinterviewDeviceButton(Z2MLinkedDeviceEntity, ButtonEntity):
    """Force a re-interview of a Zigbee device."""

    _attr_translation_key = "reinterview_device"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub: Z2MHub, ieee_address: str, ha_device_id: str) -> None:
        super().__init__(hub, ieee_address, ha_device_id)
        self._attr_unique_id = f"{hub.entry_id}_{ieee_address}_reinterview"

    async def async_press(self) -> None:
        await self._hub.async_reinterview_device(self._ieee_address)
