"""Typed representations of parsed Zigbee2MQTT MQTT payloads.

Keeping these as dataclasses (instead of passing raw dicts around) gives every
entity a typed, discoverable contract for "what fields exist", and means that
if Zigbee2MQTT ever renames a key, there is one place to fix it rather than
every entity file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(slots=True)
class BridgeInfo:
    """Parsed payload of <base_topic>/bridge/info."""

    version: str | None = None
    commit: str | None = None
    coordinator: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    log_level: str | None = None
    permit_join: bool = False
    permit_join_end: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Z2MDevice:
    """One entry of <base_topic>/bridge/devices.

    model_id is the device's own raw Zigbee-protocol model string (e.g.
    "lumi.plug") - it is NOT a Zigbee2MQTT catalog identifier and isn't
    useful for looking anything up on zigbee2mqtt.io. definition_model is
    the separate, nested "definition.model" field (e.g. "WXKG01LM") that
    Zigbee2MQTT's own device database and image CDN key off; it's None for
    devices Zigbee2MQTT hasn't matched to a known definition.
    """

    ieee_address: str
    friendly_name: str
    type: str | None = None
    model_id: str | None = None
    definition_model: str | None = None
    power_source: str | None = None
    software_build_id: str | None = None
    date_code: str | None = None
    supported: bool = True
    disabled: bool = False
    interview_completed: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Z2MGroup:
    """One entry of <base_topic>/bridge/groups."""

    id: int
    friendly_name: str
    members: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class NetworkMapResult:
    """Result of a networkmap bridge request."""

    refreshed_at: datetime
    type: str
    value: Any


@dataclass(slots=True)
class DeviceAvailability:
    """Parsed payload of <base_topic>/<friendly_name>/availability."""

    state: Literal["online", "offline"]
    since: datetime


@dataclass(slots=True)
class DeviceOtaState:
    """The "update" object embedded in a device's state payload, if present."""

    state: str | None = None
    progress: int | None = None
    remaining_time: int | None = None


@dataclass(frozen=True, slots=True)
class DeviceLinkedPayload:
    """Dispatcher payload sent when a device becomes linkable to an HA device."""

    ieee_address: str
    ha_device_id: str


@dataclass(slots=True)
class OfflineDevice:
    """One entry in the offline-devices sensor's attribute list."""

    ieee_address: str
    friendly_name: str
    detection: Literal["availability", "last_seen"]
    since: datetime


@dataclass(slots=True)
class BatteryLowDevice:
    """One entry in the battery-low sensor's attribute list."""

    ieee_address: str
    friendly_name: str
    battery: int


@dataclass(slots=True)
class LowLqiDevice:
    """One entry in the low-link-quality sensor's attribute list."""

    ieee_address: str
    friendly_name: str
    linkquality: int


@dataclass(slots=True)
class OtaAvailableDevice:
    """One entry in the OTA-update-available sensor's attribute list."""

    ieee_address: str
    friendly_name: str
