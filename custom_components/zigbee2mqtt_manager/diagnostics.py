"""Diagnostics support for Zigbee2MQTT Manager.

No redaction is applied: nothing stored here is a credential (the MQTT
broker's own credentials live in HA core's separate `mqtt` config entry, not
this one), and the device-linking fields below are exactly what's needed to
debug the integration's highest-risk mechanism (see device_link.py) - hiding
ieee_addresses or device ids would defeat that purpose.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import Z2MManagerConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Z2MManagerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for one Zigbee2MQTT instance."""
    hub = entry.runtime_data

    return {
        "entry": {
            "title": entry.title,
            "base_topic": hub.base_topic,
            "options": dict(entry.options),
        },
        "bridge": {
            "online": hub.bridge_online,
            "info": asdict(hub.bridge_info) if hub.bridge_info is not None else None,
            "groups": [asdict(group) for group in hub.groups.values()],
        },
        "devices": {
            "count": len(hub.devices),
            "devices": [asdict(device) for device in hub.devices.values()],
            "ota_state": {ieee_address: asdict(state) for ieee_address, state in hub.device_ota.items()},
            "offline": [asdict(device) for device in hub.compute_offline_devices()],
        },
        "device_linking": {
            "link_cache": {
                ieee_address: {"ha_device_id": link.ha_device_id, "method": link.method}
                for ieee_address, link in hub._link_cache.items()
            },
            "device_id_to_ieee": dict(hub.device_id_to_ieee),
        },
        "networkmap": (
            {
                "refreshed_at": hub.last_networkmap.refreshed_at.isoformat(),
                "type": hub.last_networkmap.type,
                # value omitted - can be a large graph for bigger networks and
                # isn't needed to debug anything this diagnostics file is for.
            }
            if hub.last_networkmap is not None
            else None
        ),
        "pending_requests": len(hub._pending),
    }
