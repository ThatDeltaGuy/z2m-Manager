"""Constants for the Zigbee2MQTT Manager integration."""

from __future__ import annotations

DOMAIN = "zigbee2mqtt_manager"

MQTT_DOMAIN = "mqtt"

# Config entry data keys (set once at setup, immutable afterwards)
CONF_BASE_TOPIC = "base_topic"
CONF_NAME = "name"

# Options keys (mutable via the options flow)
CONF_OFFLINE_THRESHOLD_MINUTES = "offline_threshold_minutes"
CONF_NETWORKMAP_INTERVAL_HOURS = "networkmap_interval_hours"
CONF_NETWORKMAP_TYPE = "networkmap_type"
CONF_NETWORKMAP_ROUTES = "networkmap_routes"
CONF_PERMIT_JOIN_DURATION = "permit_join_duration"
CONF_BATTERY_LOW_THRESHOLD_PERCENT = "battery_low_threshold_percent"
CONF_LOW_LQI_THRESHOLD = "low_lqi_threshold"
CONF_OTA_CHECK_INTERVAL_DAYS = "ota_check_interval_days"
CONF_REMOVE_BUTTON_ENABLED_BY_DEFAULT = "remove_button_enabled_by_default"
CONF_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT = "reinterview_button_enabled_by_default"

# Defaults
DEFAULT_BASE_TOPIC = "zigbee2mqtt"
DEFAULT_OFFLINE_THRESHOLD_MINUTES = 15
DEFAULT_NETWORKMAP_INTERVAL_HOURS = 1
DEFAULT_NETWORKMAP_TYPE = "raw"
DEFAULT_NETWORKMAP_ROUTES = False
DEFAULT_PERMIT_JOIN_DURATION = 254
DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT = 15
DEFAULT_LOW_LQI_THRESHOLD = 50
DEFAULT_OTA_CHECK_INTERVAL_DAYS = 1
# Both False: remove/re-interview default to disabled in the entity
# registry so they can't be pressed by accident from a dashboard - the user
# can flip either back on per-instance via the options flow.
DEFAULT_REMOVE_BUTTON_ENABLED_BY_DEFAULT = False
DEFAULT_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT = False

NETWORKMAP_TYPES = ["raw", "graphviz", "plantuml"]
LOG_LEVELS = ["debug", "info", "warning", "error"]

# Zigbee2MQTT's bridge/devices "type" value for the coordinator itself. It
# has no battery, no meaningful self-referential link quality, and its
# online/offline status is already covered by the bridge connectivity sensor
# (bridge/state) - so it's excluded from the offline/battery/LQI aggregate
# sensors, which would otherwise misreport it via a perpetually-stale
# last_seen (coordinators don't send Zigbee messages to themselves, so
# last_seen for the coordinator entry rarely if ever updates).
COORDINATOR_DEVICE_TYPE = "Coordinator"

# Bridge request command names (published to "<base_topic>/bridge/request/<command>")
CMD_PERMIT_JOIN = "permit_join"
CMD_RESTART = "restart"
CMD_OPTIONS = "options"
CMD_NETWORKMAP = "networkmap"
CMD_DEVICE_RENAME = "device/rename"
CMD_DEVICE_REMOVE = "device/remove"
CMD_DEVICE_INTERVIEW = "device/interview"
CMD_DEVICE_OTA_CHECK = "device/ota_update/check"
CMD_DEVICE_OTA_UPDATE = "device/ota_update/update"

# Request timeouts (seconds)
REQUEST_TIMEOUT_DEFAULT = 10.0
# Generating a network map (especially with routes=true) can take well over
# 90s on a larger mesh
REQUEST_TIMEOUT_NETWORKMAP = 300.0
REQUEST_TIMEOUT_OTA_CHECK = 30.0
REQUEST_TIMEOUT_OTA_UPDATE = 600.0
MQTT_CLIENT_WAIT_TIMEOUT = 10.0
CONFIG_FLOW_MQTT_WAIT_TIMEOUT = 5.0

# Device-link reconciliation debounce (seconds)
LINK_RECONCILE_DEBOUNCE = 0.5


# --- Dispatcher signal names -------------------------------------------------
# All signal-name construction goes through these helpers rather than inline
# f-strings at call sites, so every producer/consumer of a signal is guaranteed
# to agree on its exact format.


def signal_bridge_info(entry_id: str) -> str:
    """Signal fired when bridge/info is (re)parsed."""
    return f"{DOMAIN}_{entry_id}_bridge_info"


def signal_bridge_state(entry_id: str) -> str:
    """Signal fired when bridge/state changes."""
    return f"{DOMAIN}_{entry_id}_bridge_state"


def signal_bridge_groups(entry_id: str) -> str:
    """Signal fired when bridge/groups is (re)parsed."""
    return f"{DOMAIN}_{entry_id}_bridge_groups"


def signal_devices(entry_id: str) -> str:
    """Signal fired when bridge/devices is (re)parsed."""
    return f"{DOMAIN}_{entry_id}_devices"


def signal_networkmap(entry_id: str) -> str:
    """Signal fired when a network map refresh completes."""
    return f"{DOMAIN}_{entry_id}_networkmap"


def signal_device_availability(entry_id: str, ieee_address: str) -> str:
    """Signal fired when a specific device's availability topic updates."""
    return f"{DOMAIN}_{entry_id}_device_{ieee_address}_availability"


def signal_device_linkable(entry_id: str) -> str:
    """Signal fired when a device becomes linkable to an existing HA device."""
    return f"{DOMAIN}_{entry_id}_device_linkable"


def signal_device_unlinkable(entry_id: str) -> str:
    """Signal fired when a device stops being linkable (or is removed)."""
    return f"{DOMAIN}_{entry_id}_device_unlinkable"


def signal_offline_candidates_changed(entry_id: str) -> str:
    """Bridge-wide signal: something compute_offline_devices() depends on changed.

    Fired alongside (not instead of) the per-device signals above whenever
    bridge/devices, any device's availability, or any device's last_seen
    updates - lets the offline-devices sensor react without subscribing to
    every individual device's own signal.
    """
    return f"{DOMAIN}_{entry_id}_offline_candidates_changed"


def signal_device_metrics_changed(entry_id: str) -> str:
    """Bridge-wide signal: a device's battery, link quality, or OTA state changed.

    Shared by the battery-low, low-LQI, and OTA-available aggregate sensors,
    the same way signal_offline_candidates_changed is shared by the
    offline-devices sensor - avoids each of those subscribing to every
    individual device's own per-device signal.
    """
    return f"{DOMAIN}_{entry_id}_device_metrics_changed"
