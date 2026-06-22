"""Best-effort lookup of the HA device Zigbee2MQTT's own MQTT discovery created.

Isolated in its own module because the exact identifier string Zigbee2MQTT's
discovery uses (Strategy 1 below) was not independently confirmed against a
live discovery payload or current Zigbee2MQTT source at the time this was
written - see the project plan for the verification step to run before
trusting it. If that string turns out to be wrong, this is the only file that
needs to change.

This module is read-only by construction: it has no code path that creates,
updates, or claims ownership of a device. That is what makes "never create a
fallback device" structurally guaranteed rather than a runtime check that
could be forgotten - find_ha_device_for_z2m_device only ever reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

#: Domain under which Home Assistant's core `mqtt` integration registers
#: devices it creates via MQTT discovery (i.e. the identifier tuple's first
#: element), regardless of which external system (Zigbee2MQTT, Tasmota, ...)
#: triggered the discovery payload.
_MQTT_INTEGRATION_DOMAIN = "mqtt"


@dataclass(frozen=True, slots=True)
class LinkResult:
    """Outcome of attempting to find the HA device Z2M's discovery created."""

    ha_device_id: str | None
    method: Literal["identifier", "friendly_name", "not_found"]


def find_ha_device_for_z2m_device(
    hass: HomeAssistant,
    *,
    ieee_address: str,
    friendly_name: str,
    mqtt_config_entry_id: str | None,
) -> LinkResult:
    """Best-effort, read-only lookup of an existing HA device for ieee_address.

    Never creates, updates, or claims a device - only reads the registry.
    """
    registry = dr.async_get(hass)

    # Strategy 1 (primary): reconstruct Zigbee2MQTT's HA-discovery identifier
    # convention. UNVERIFIED against a live payload - see module docstring.
    device = registry.async_get_device(
        identifiers={(_MQTT_INTEGRATION_DOMAIN, f"zigbee2mqtt_{ieee_address}")}
    )
    if device is not None:
        return LinkResult(device.id, "identifier")

    # Strategy 2 (fallback): name match among devices owned by the `mqtt`
    # integration's config entry. Z2M's discovery payload sets the HA
    # device's name to the device's friendly_name (or a user override in
    # Z2M), so this is heuristic and can mismatch after a Z2M-side rename
    # that HA's discovery hasn't yet republished for - best-effort only.
    if mqtt_config_entry_id:
        for candidate in dr.async_entries_for_config_entry(registry, mqtt_config_entry_id):
            if friendly_name in (candidate.name_by_user, candidate.name):
                return LinkResult(candidate.id, "friendly_name")

    return LinkResult(None, "not_found")


def async_get_mqtt_config_entry_id(hass: HomeAssistant) -> str | None:
    """Return the loaded `mqtt` integration's config entry id, if exactly one exists.

    Strategy 2 above is skipped (not an error) when this returns None - either
    because the `mqtt` integration somehow isn't loaded (shouldn't happen,
    since it's a hard dependency) or, in the unusual case of more than one
    `mqtt` config entry, because it's unclear which one to search.
    """
    entries = hass.config_entries.async_entries(_MQTT_INTEGRATION_DOMAIN)
    if len(entries) != 1:
        return None
    return entries[0].entry_id
