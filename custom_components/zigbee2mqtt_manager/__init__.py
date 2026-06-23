"""The Zigbee2MQTT Manager integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_BASE_TOPIC,
    CONF_BATTERY_LOW_THRESHOLD_PERCENT,
    CONF_LOW_LQI_THRESHOLD,
    CONF_NAME,
    CONF_NETWORKMAP_INTERVAL_MINUTES,
    CONF_NETWORKMAP_ROUTES,
    CONF_NETWORKMAP_TYPE,
    CONF_OFFLINE_THRESHOLD_MINUTES,
    CONF_OTA_CHECK_INTERVAL_MINUTES,
    CONF_PERMIT_JOIN_DURATION,
    DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT,
    DEFAULT_LOW_LQI_THRESHOLD,
    DEFAULT_NETWORKMAP_ROUTES,
    DEFAULT_NETWORKMAP_TYPE,
    DEFAULT_OFFLINE_THRESHOLD_MINUTES,
    DEFAULT_OTA_CHECK_INTERVAL_MINUTES,
    DEFAULT_PERMIT_JOIN_DURATION,
    DOMAIN,
)
from .hub import Z2MHub, Z2MMqttUnavailableError
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

# This integration is config-entry-only (no YAML setup) - this tells
# hassfest/HA that explicitly, and makes any accidental YAML config under
# the domain key fail loudly with a message pointing at the UI instead of
# being silently ignored.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type Z2MManagerConfigEntry = ConfigEntry[Z2MHub]

# Platforms are appended here as each is built out (see the integration's
# build-order milestones); keeping this list short while a platform module
# does not exist yet avoids forwarding setup to a module with no entities.
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once, regardless of how many instances get configured.

    This integration is config-entry-only (no YAML setup), but async_setup is
    still the standard one-time-per-HA-run hook for domain-wide service
    registration - unlike async_setup_entry, it doesn't re-run per instance.
    """
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: Z2MManagerConfigEntry) -> bool:
    """Set up a Zigbee2MQTT instance from a config entry."""
    hub = Z2MHub(
        hass,
        entry.entry_id,
        entry.data[CONF_BASE_TOPIC],
        entry.data[CONF_NAME],
        permit_join_duration=entry.options.get(CONF_PERMIT_JOIN_DURATION, DEFAULT_PERMIT_JOIN_DURATION),
        offline_threshold_minutes=entry.options.get(
            CONF_OFFLINE_THRESHOLD_MINUTES, DEFAULT_OFFLINE_THRESHOLD_MINUTES
        ),
        networkmap_interval_minutes=entry.options.get(CONF_NETWORKMAP_INTERVAL_MINUTES, 0),
        networkmap_type=entry.options.get(CONF_NETWORKMAP_TYPE, DEFAULT_NETWORKMAP_TYPE),
        networkmap_routes=entry.options.get(CONF_NETWORKMAP_ROUTES, DEFAULT_NETWORKMAP_ROUTES),
        battery_low_threshold_percent=entry.options.get(
            CONF_BATTERY_LOW_THRESHOLD_PERCENT, DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT
        ),
        low_lqi_threshold=entry.options.get(CONF_LOW_LQI_THRESHOLD, DEFAULT_LOW_LQI_THRESHOLD),
        ota_check_interval_minutes=entry.options.get(
            CONF_OTA_CHECK_INTERVAL_MINUTES, DEFAULT_OTA_CHECK_INTERVAL_MINUTES
        ),
    )

    try:
        await hub.async_setup()
    except Z2MMqttUnavailableError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: Z2MManagerConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_unload()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: Z2MManagerConfigEntry) -> None:
    """Apply options-flow changes live, without reloading the config entry."""
    await entry.runtime_data.async_update_options(entry.options)
