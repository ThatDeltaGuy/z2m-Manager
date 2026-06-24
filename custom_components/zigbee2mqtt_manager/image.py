"""Image platform for Zigbee2MQTT Manager.

Per-device device-photo entity, created only for devices device_link.py has
resolved an existing HA device for (see hub.py's link reconciliation) *and*
that have a known catalog model - Zigbee2MQTT's bridge/devices "model_id"
field is the device's own raw Zigbee-protocol model string (e.g.
"lumi.plug"), not a catalog identifier; the field the image CDN keys off is
the separate, nested "definition.model" (see models.py's Z2MDevice).
"""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import Z2MManagerConfigEntry
from .const import signal_device_linkable, signal_device_unlinkable, signal_devices
from .entity import Z2MLinkedDeviceEntity, async_attach_to_linked_device
from .hub import Z2MHub
from .models import DeviceLinkedPayload

# Confirmed directly against Zigbee2MQTT's own documentation source (every
# docs/devices/<model>.md page in the zigbee2mqtt.io repo references exactly
# images/devices/<model>.png for that model) rather than inferred - but it
# is still an undocumented convention, not a public API contract, so worth
# re-checking here first if device images ever stop resolving.
_IMAGE_BASE_URL = "https://www.zigbee2mqtt.io/images/devices"


def _device_image_url(definition_model: str) -> str:
    return f"{_IMAGE_BASE_URL}/{quote(definition_model, safe='')}.png"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up per-device image entities as devices link *and* gain a known model.

    Unlike the remove/re-interview buttons, this entity depends on two
    independent things both being true (linked, and Zigbee2MQTT having
    identified a catalog model) - either can become true after the other,
    since device linking and Zigbee2MQTT's own interview/identification
    happen independently. created_for tracks which devices already have an
    entity so the broader signal_devices listener (which re-checks every
    device on every bridge/devices reparse, not just the one that changed)
    doesn't create duplicates.
    """
    hub = entry.runtime_data
    created_for: set[str] = set()

    @callback
    def _maybe_create(ieee_address: str) -> None:
        if ieee_address in created_for:
            return
        link = hub._link_cache.get(ieee_address)
        if link is None or link.ha_device_id is None:
            return
        device = hub.devices.get(ieee_address)
        if device is None or not device.definition_model:
            return
        created_for.add(ieee_address)
        entity = Z2MDeviceImageEntity(hub, ieee_address, link.ha_device_id, device.definition_model)
        async_add_entities([entity])
        async_attach_to_linked_device(
            hass, platform="image", unique_id=entity.unique_id, ha_device_id=link.ha_device_id
        )

    @callback
    def _async_device_linkable(payload: DeviceLinkedPayload) -> None:
        _maybe_create(payload.ieee_address)

    @callback
    def _async_devices_updated(_devices: dict) -> None:
        for ieee_address in hub.devices:
            _maybe_create(ieee_address)

    @callback
    def _async_device_unlinkable(ieee_address: str) -> None:
        # The entity itself self-removes via Z2MLinkedDeviceEntity's own
        # unlinkable handling - this just clears our bookkeeping so a
        # device that later re-links gets a fresh entity instead of being
        # silently skipped as "already created".
        created_for.discard(ieee_address)

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_device_linkable(hub.entry_id), _async_device_linkable)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_devices(hub.entry_id), _async_devices_updated)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_device_unlinkable(hub.entry_id), _async_device_unlinkable)
    )

    for ieee_address in list(hub.devices):
        _maybe_create(ieee_address)


class Z2MDeviceImageEntity(Z2MLinkedDeviceEntity, ImageEntity):
    """A linked device's catalog photo, served from Zigbee2MQTT's own CDN.

    The model (and therefore the image) is fixed at construction time - if
    Zigbee2MQTT later re-identifies the device as a different model, this
    entity would need to be recreated, not updated in place. That's an
    acceptable simplification: a device's model essentially never changes
    after Zigbee2MQTT has already interviewed and identified it once.
    """

    _attr_translation_key = "device_image"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: Z2MHub, ieee_address: str, ha_device_id: str, definition_model: str) -> None:
        Z2MLinkedDeviceEntity.__init__(self, hub, ieee_address, ha_device_id)
        ImageEntity.__init__(self, hub.hass)
        self._attr_unique_id = f"{hub.entry_id}_{ieee_address}_image"
        self._attr_image_url = _device_image_url(definition_model)
        # ImageEntity.state is derived from this (it's @final, so it can't
        # be overridden directly) - without it the entity's state just
        # shows "unknown" forever, even though the image itself is valid.
        # The image URL is fixed at construction time (see class docstring),
        # so "now" at construction is the one and only meaningful update.
        self._attr_image_last_updated = dt_util.utcnow()
