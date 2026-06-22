"""Update platform for Zigbee2MQTT Manager: per-device OTA firmware status.

Only created for devices device_link.py has resolved an existing HA device
for (see hub.py's link reconciliation) - per the project's decision, devices
without a linkable HA device get none of this milestone's per-device extras.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Z2MManagerConfigEntry
from .const import signal_device_linkable, signal_device_state
from .entity import Z2MLinkedDeviceEntity
from .hub import Z2MHub
from .models import DeviceLinkedPayload


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Z2MManagerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up OTA update entities for devices already linkable, and dynamically as more link."""
    hub = entry.runtime_data

    @callback
    def _async_device_linkable(payload: DeviceLinkedPayload) -> None:
        async_add_entities([Z2MOtaUpdateEntity(hub, payload.ieee_address, payload.ha_device_id)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_device_linkable(hub.entry_id), _async_device_linkable)
    )

    async_add_entities(
        Z2MOtaUpdateEntity(hub, ieee_address, link.ha_device_id)
        for ieee_address, link in hub._link_cache.items()
        if link.ha_device_id is not None
    )


class Z2MOtaUpdateEntity(Z2MLinkedDeviceEntity, UpdateEntity):
    """OTA firmware update status/install for one Zigbee device."""

    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_translation_key = "ota_update"

    def __init__(self, hub: Z2MHub, ieee_address: str, ha_device_id: str) -> None:
        super().__init__(hub, ieee_address, ha_device_id)
        self._attr_unique_id = f"{hub.entry_id}_{ieee_address}_ota_update"

    @property
    def installed_version(self) -> str | None:
        # Zigbee2MQTT has no clean "currently installed version" string of
        # its own ahead of an explicit OTA check - software_build_id is the
        # closest analogue it exposes. Documented approximation, not a typo.
        device = self._hub.devices.get(self._ieee_address)
        return device.software_build_id if device else None

    @property
    def latest_version(self) -> str | None:
        ota = self._hub.device_ota.get(self._ieee_address)
        if ota is None or ota.state not in ("available", "updating"):
            return self.installed_version
        # Z2M doesn't give a version string for "what's available" either.
        # UpdateEntity needs latest_version != installed_version to show
        # "update available" in the UI, so use a sentinel - the "check for
        # update" verb (ota_check service) is what surfaces real detail.
        return "update_available"

    @property
    def in_progress(self) -> bool:
        ota = self._hub.device_ota.get(self._ieee_address)
        return ota is not None and ota.state == "updating"

    @property
    def update_percentage(self) -> int | None:
        ota = self._hub.device_ota.get(self._ieee_address)
        return ota.progress if ota is not None else None

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        # "Check, don't install" has no native UpdateEntity verb - that's the
        # ota_check service, not a button here. This is the install action.
        await self._hub.async_ota_update(self._ieee_address)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_device_state(self._hub.entry_id, self._ieee_address),
                self._handle_state_update,
            )
        )

    @callback
    def _handle_state_update(self, _ota: Any) -> None:
        self.async_write_ha_state()
