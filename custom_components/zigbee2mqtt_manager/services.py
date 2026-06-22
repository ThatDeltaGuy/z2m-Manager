"""Service registration for Zigbee2MQTT Manager.

Registered once, domain-wide (see __init__.py's async_setup) rather than per
config entry - the services exist regardless of how many Zigbee2MQTT
instances are configured, and each call resolves which hub to act on from
its own target fields rather than from a fixed entry.

Z2MRequestError/Z2MRequestTimeoutError (Zigbee2MQTT rejected or never
answered a request) are deliberately left to propagate uncaught here, the
same way button.py and update.py already let them propagate from entity
actions - introducing a different error-handling convention only in this
file would be inconsistent for no real benefit. ServiceValidationError is
used only for the distinct case of a bad target (an id that doesn't resolve
to a real hub/device), which HA's UI renders as a validation problem rather
than a generic failure.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, NETWORKMAP_TYPES
from .hub import Z2MHub

ATTR_DEVICE_ID = "device_id"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_TO_NAME = "to_name"
ATTR_FORCE = "force"
ATTR_BLOCK = "block"
ATTR_TIME = "time"
ATTR_OPTIONS = "options"
ATTR_COMMAND = "command"
ATTR_PAYLOAD = "payload"
ATTR_TYPE = "type"
ATTR_ROUTES = "routes"
ATTR_UPDATE_AVAILABLE = "update_available"

SERVICE_RENAME_DEVICE = "rename_device"
SERVICE_REMOVE_DEVICE = "remove_device"
SERVICE_REINTERVIEW_DEVICE = "reinterview_device"
SERVICE_PERMIT_JOIN = "permit_join"
SERVICE_RESTART = "restart"
SERVICE_SET_OPTIONS = "set_options"
SERVICE_OTA_CHECK = "ota_check"
SERVICE_OTA_UPDATE = "ota_update"
SERVICE_REFRESH_NETWORKMAP = "refresh_networkmap"
SERVICE_RAW_COMMAND = "raw_command"


def _async_get_hub(hass: HomeAssistant, config_entry_id: str) -> Z2MHub:
    """Resolve a config_entry_id target to its hub."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"'{config_entry_id}' is not a Zigbee2MQTT Manager config entry")
    return entry.runtime_data


def _async_get_hub_and_ieee_for_device(hass: HomeAssistant, device_id: str) -> tuple[Z2MHub, str]:
    """Find which configured Zigbee2MQTT instance's linked device this is.

    Searches every loaded hub's device_id_to_ieee reverse-lookup (built for
    free during link reconciliation - see hub.py) rather than parsing it out
    of a unique_id string.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        hub: Z2MHub | None = getattr(entry, "runtime_data", None)
        if hub is None:
            continue
        ieee_address = hub.device_id_to_ieee.get(device_id)
        if ieee_address is not None:
            return hub, ieee_address
    raise ServiceValidationError(
        f"'{device_id}' is not currently linked to a device on any configured Zigbee2MQTT instance"
    )


def _resolve_scoped_device(hub: Z2MHub, device_id: str | None) -> str | None:
    """Resolve an optional permit_join device target within a specific hub.

    Unlike the per-device services, permit_join's config_entry_id already
    names the hub - this only needs to confirm the given device actually
    belongs to that same instance.
    """
    if device_id is None:
        return None
    ieee_address = hub.device_id_to_ieee.get(device_id)
    if ieee_address is None:
        raise ServiceValidationError(
            f"'{device_id}' is not currently linked to a device on this Zigbee2MQTT instance"
        )
    return ieee_address


def async_setup_services(hass: HomeAssistant) -> None:
    """Register all Zigbee2MQTT Manager services. Called once from async_setup."""

    async def _rename_device(call: ServiceCall) -> None:
        hub, ieee_address = _async_get_hub_and_ieee_for_device(hass, call.data[ATTR_DEVICE_ID])
        await hub.async_rename_device(ieee_address, call.data[ATTR_TO_NAME])

    async def _remove_device(call: ServiceCall) -> None:
        hub, ieee_address = _async_get_hub_and_ieee_for_device(hass, call.data[ATTR_DEVICE_ID])
        await hub.async_remove_device(ieee_address, force=call.data[ATTR_FORCE], block=call.data[ATTR_BLOCK])

    async def _reinterview_device(call: ServiceCall) -> None:
        hub, ieee_address = _async_get_hub_and_ieee_for_device(hass, call.data[ATTR_DEVICE_ID])
        await hub.async_reinterview_device(ieee_address)

    async def _permit_join(call: ServiceCall) -> None:
        hub = _async_get_hub(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        device = _resolve_scoped_device(hub, call.data.get(ATTR_DEVICE_ID))
        await hub.async_permit_join(call.data[ATTR_TIME], device=device)

    async def _restart(call: ServiceCall) -> None:
        hub = _async_get_hub(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        await hub.async_restart()

    async def _set_options(call: ServiceCall) -> None:
        hub = _async_get_hub(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        await hub.async_raw_passthrough("options", {"options": call.data[ATTR_OPTIONS]})

    async def _ota_check(call: ServiceCall) -> ServiceResponse:
        _hub, ieee_address = _async_get_hub_and_ieee_for_device(hass, call.data[ATTR_DEVICE_ID])
        update_available = await _hub.async_ota_check(ieee_address)
        return {ATTR_UPDATE_AVAILABLE: update_available}

    async def _ota_update(call: ServiceCall) -> None:
        hub, ieee_address = _async_get_hub_and_ieee_for_device(hass, call.data[ATTR_DEVICE_ID])
        await hub.async_ota_update(ieee_address)

    async def _refresh_networkmap(call: ServiceCall) -> None:
        hub = _async_get_hub(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        await hub.async_refresh_networkmap(type=call.data.get(ATTR_TYPE), routes=call.data.get(ATTR_ROUTES))

    async def _raw_command(call: ServiceCall) -> ServiceResponse:
        hub = _async_get_hub(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        data = await hub.async_raw_passthrough(call.data[ATTR_COMMAND], call.data.get(ATTR_PAYLOAD, {}))
        return {"data": data}

    hass.services.async_register(
        DOMAIN,
        SERVICE_RENAME_DEVICE,
        _rename_device,
        schema=vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_TO_NAME): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_DEVICE,
        _remove_device,
        schema=vol.Schema(
            {
                vol.Required(ATTR_DEVICE_ID): cv.string,
                vol.Optional(ATTR_FORCE, default=False): cv.boolean,
                vol.Optional(ATTR_BLOCK, default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REINTERVIEW_DEVICE,
        _reinterview_device,
        schema=vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PERMIT_JOIN,
        _permit_join,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Optional(ATTR_TIME, default=254): vol.All(vol.Coerce(int), vol.Range(min=0, max=254)),
                vol.Optional(ATTR_DEVICE_ID): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTART,
        _restart,
        schema=vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OPTIONS,
        _set_options,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Required(ATTR_OPTIONS): dict,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_OTA_CHECK,
        _ota_check,
        schema=vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_OTA_UPDATE,
        _ota_update,
        schema=vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_NETWORKMAP,
        _refresh_networkmap,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Optional(ATTR_TYPE): vol.In(NETWORKMAP_TYPES),
                vol.Optional(ATTR_ROUTES): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RAW_COMMAND,
        _raw_command,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
                vol.Required(ATTR_COMMAND): cv.string,
                vol.Optional(ATTR_PAYLOAD, default=dict): dict,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
