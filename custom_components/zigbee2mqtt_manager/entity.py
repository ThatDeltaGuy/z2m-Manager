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

    This device is one this integration legitimately owns (it represents
    "the bridge, as managed by this integration"), unlike the per-device
    extras added in a later milestone, which attach to a device created by
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

        `available` defaults to tracking hub.bridge_online, but nothing else
        makes that change visible on its own - a subclass whose own data
        signal happens not to fire at the same time would otherwise keep
        showing a stale availability. Subclasses that add their own
        async_added_to_hass must call super().async_added_to_hass().
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
    directly to the device device_link.py already found, so this entity
    attaches to it without creating or claiming ownership of that device
    (see device_link.py and the project plan for why this matters).

    Persisting the link into the entity registry's device_id field is *not*
    done here in async_added_to_hass: that hook only runs for live
    (enabled) entities, but some of these entities are disabled by default
    (e.g. remove/re-interview - see button.py), and HA's own entity
    registration determines device_id purely from entity.device_info (which
    this class deliberately never sets) regardless of enabled state. A
    disabled instance would otherwise be registered with no device
    association at all, even though self.device_entry is set correctly.
    Platform setup functions must call async_attach_to_linked_device (below)
    for every instance they create, enabled or not - see button.py/image.py.

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

    def _device_prefixed_suggestion(self, own_suggestion: str | None) -> str | None:
        if self.device_entry is None or not own_suggestion:
            return own_suggestion
        device_name = self.device_entry.name_by_user or self.device_entry.name
        if not device_name:
            return own_suggestion
        return f"{device_name} {own_suggestion}"

    @property
    def suggested_object_id(self) -> str | None:
        """Prefix the entity_id suggestion with the linked device's name.

        entity_platform's own device-name-prefixing only triggers off
        device_info, which this class deliberately never sets (see class
        docstring) - without this override every device's per-device entity
        of a given kind would suggest the same bare object_id (e.g.
        "firmware"), relying on the registry's collision suffixing ("_2",
        "_3", ...) instead of a meaningful per-device entity_id.

        Only takes effect on HA Core versions that don't read
        internal_integration_suggested_object_id below (kept for backwards
        compatibility) - on versions that do, this value would otherwise be
        treated as a mere "object_id_base" and get device name *and area
        name* re-combined on top of it a second time by the entity
        registry, producing entity_ids like
        "bedroom_bedroom_light_1_bedroom_light_1_image" instead of
        "bedroom_light_1_image" for a device named "Bedroom Light 1" in a
        "Bedroom" area.
        """
        return self._device_prefixed_suggestion(super().suggested_object_id)

    @property
    def internal_integration_suggested_object_id(self) -> str | None:
        """Same suggestion as suggested_object_id, for newer HA Core versions.

        Newer HA Core (see entity_platform._async_derive_object_ids) only
        treats a value from here as a true "suggested_object_id" - one that
        bypasses the registry's own automatic area+device+entity name
        combination. A value from the suggested_object_id property above is
        instead treated as an "object_id_base", which *does* get that
        automatic combination applied on top of it, double (and once an
        area is involved, triple) prefixing the device's name. See
        suggested_object_id's docstring for the resulting entity_id this
        was producing before this property was added.
        """
        return self._device_prefixed_suggestion(super().suggested_object_id)

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
            self.hass.async_create_task(self.async_remove(force_remove=True))


def async_attach_to_linked_device(
    hass: HomeAssistant, *, platform: str, unique_id: str, ha_device_id: str
) -> None:
    """Set a just-created entity's device_id in the registry.

    Must be called once after async_add_entities() for every
    Z2MLinkedDeviceEntity instance, regardless of whether it ends up enabled
    or disabled - see that class's docstring for why this can't be done in
    async_added_to_hass instead. platform is the entity platform's own
    domain (e.g. "button", "image"), not this integration's domain.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
    if entity_id is not None:
        registry.async_update_entity(entity_id, device_id=ha_device_id)
