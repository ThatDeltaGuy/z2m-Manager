"""Common entity base classes for Zigbee2MQTT Manager entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, signal_bridge_state, signal_device_unlinkable
from .hub import Z2MHub


class Z2MBridgeEntity(Entity):
    """Base for entities representing one Zigbee2MQTT bridge instance.

    This device is one this integration legitimately owns, unlike the
    per-device extras below, which attach to a device created by
    Zigbee2MQTT's own MQTT discovery and must never use device_info.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: Z2MHub) -> None:
        self._hub = hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.entry_id)},
            name=hub.name,
            manufacturer="Zigbee2MQTT",
            model="Bridge",
        )

    @property
    def available(self) -> bool:
        """Most bridge entities are only meaningful while the bridge is online."""
        return self._hub.bridge_online

    async def async_added_to_hass(self) -> None:
        """Re-publish state whenever bridge online/offline status changes.

        Subclasses with their own async_added_to_hass must call
        super().async_added_to_hass().
        """
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_bridge_state(self._hub.entry_id),
                self._handle_bridge_state_for_availability,
            )
        )

    @callback
    def _handle_bridge_state_for_availability(self, _online: bool) -> None:
        self.async_write_ha_state()


class Z2MLinkedDeviceEntity(Entity):
    """Base for per-device entities attached to an existing Z2M-discovered device.

    Never sets device_info/identifiers - self.device_entry is assigned
    directly to the device device_link.py found, attaching to it without
    claiming ownership. Platform setup functions must call
    async_attach_to_linked_device (below) for every instance they create,
    enabled or not, to set device_id in the registry - see button.py/image.py.

    Only created for devices that are currently linkable (see hub.py's link
    reconciliation), and self-removes the moment that stops being true -
    subclasses with their own async_added_to_hass must call
    super().async_added_to_hass().
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: Z2MHub, ieee_address: str, ha_device_id: str) -> None:
        self._hub = hub
        self._ieee_address = ieee_address
        self._ha_device_id = ha_device_id
        self.device_entry = dr.async_get(hub.hass).async_get(ha_device_id)

    @property
    def available(self) -> bool:
        return self._hub.bridge_online

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_unlinkable(self._hub.entry_id),
                self._handle_unlinkable,
            )
        )

    @callback
    def _handle_unlinkable(self, ieee_address: str) -> None:
        if ieee_address == self._ieee_address:
            self.hass.async_create_task(self._async_remove_fully())

    async def _async_remove_fully(self) -> None:
        # Entity.async_remove only clears live state - it never deletes the
        # entity registry entry, so that has to be done explicitly too.
        entity_id = self.entity_id
        await self.async_remove(force_remove=True)
        registry = er.async_get(self.hass)
        if registry.async_get(entity_id) is not None:
            registry.async_remove(entity_id)


def async_attach_to_linked_device(
    hass: HomeAssistant, *, platform: str, unique_id: str, ha_device_id: str
) -> None:
    """Set a just-created entity's device_id in the registry.

    Must be called once after async_add_entities() for every
    Z2MLinkedDeviceEntity instance, enabled or disabled. platform is the
    entity platform's own domain (e.g. "button", "image"), not this
    integration's domain.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is not None:
        registry.async_update_entity(entity_id, device_id=ha_device_id)


def async_remove_if_disabled(hass: HomeAssistant, *, platform: str, unique_id: str) -> None:
    """Remove a per-device entity's registry entry if it's currently disabled.

    Disabled entities have no live object, so Z2MLinkedDeviceEntity's own
    unlinkable handling (which runs in async_added_to_hass) never fires for
    them. Platform setup functions must call this on signal_device_unlinkable
    for every unique_id they own, alongside that live self-removal path -
    HA's own device-removal cascade only deletes entities that share the
    removed device's own config entry, which these never do.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is None:
        return
    entry = registry.async_get(entity_id)
    if entry is not None and entry.disabled_by is not None:
        registry.async_remove(entity_id)
