"""Constants for the Zigbee2MQTT Manager integration."""

from __future__ import annotations

DOMAIN = "zigbee2mqtt_manager"

MQTT_DOMAIN = "mqtt"

# Config entry data keys (set once at setup, immutable afterwards)
CONF_BASE_TOPIC = "base_topic"
CONF_NAME = "name"

# Options keys (mutable via the options flow)
CONF_OFFLINE_THRESHOLD_MINUTES = "offline_threshold_minutes"
CONF_NETWORKMAP_INTERVAL_MINUTES = "networkmap_interval_minutes"
CONF_NETWORKMAP_TYPE = "networkmap_type"
CONF_NETWORKMAP_ROUTES = "networkmap_routes"
CONF_PERMIT_JOIN_DURATION = "permit_join_duration"

# Defaults
DEFAULT_BASE_TOPIC = "zigbee2mqtt"
DEFAULT_OFFLINE_THRESHOLD_MINUTES = 15
DEFAULT_NETWORKMAP_INTERVAL_MINUTES = 60
DEFAULT_NETWORKMAP_TYPE = "raw"
DEFAULT_NETWORKMAP_ROUTES = False
DEFAULT_PERMIT_JOIN_DURATION = 254

NETWORKMAP_TYPES = ["raw", "graphviz", "plantuml"]
LOG_LEVELS = ["debug", "info", "warning", "error"]

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
REQUEST_TIMEOUT_NETWORKMAP = 30.0
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


def signal_device_state(entry_id: str, ieee_address: str) -> str:
    """Signal fired when a specific device's state topic updates."""
    return f"{DOMAIN}_{entry_id}_device_{ieee_address}_state"


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
