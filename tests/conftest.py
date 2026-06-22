"""Shared pytest fixtures for the Zigbee2MQTT Manager test suite."""

from __future__ import annotations

import asyncio
import json
import socket as _socket_module

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import (
    CONF_BASE_TOPIC,
    CONF_NAME,
    DOMAIN,
    LINK_RECONCILE_DEBOUNCE,
)

#: A device already known to Zigbee2MQTT (via bridge/devices) and already
#: linked to an existing HA device (via Zigbee2MQTT's own MQTT discovery,
#: simulated here) - the scenario every per-device entity/service test needs.
IEEE_ADDRESS = "0x00124b0023d4f1a2"
FRIENDLY_NAME = "living_room_light"

#: How long to wait after firing bridge/devices for link reconciliation's
#: debounce timer (see hub.py) to fire and resolve the link.
SETTLE_SECONDS = LINK_RECONCILE_DEBOUNCE + 0.3

# --- Windows + pytest-socket + asyncio ProactorEventLoop compatibility -----
#
# pytest-homeassistant-custom-component unconditionally calls
# pytest_socket.disable_socket(allow_unix_socket=True) before every test, to
# mirror upstream HA's test config and catch accidental real network calls.
# On Windows, asyncio's ProactorEventLoop (which HA's own runner deliberately
# selects) needs a loopback AF_INET TCP socket pair internally just to
# construct itself (there's no native AF_UNIX socketpair on Windows), and
# that blanket block rejects it - it isn't a Unix socket, so even that
# plugin's allow_unix_socket=True doesn't help, and no CLI flag or fixture
# can override it since the call is unconditional.
#
# Rather than disabling the safety net altogether, patch socket.socketpair
# (which is what asyncio's self-pipe setup calls) to briefly restore the real
# socket.socket class for just that one internal call, then put
# pytest-socket's guard back immediately after. Real application/test code
# calling socket.socket(...) directly is still blocked.
_real_socket_class = _socket_module.socket
_original_socketpair = _socket_module.socketpair


def _socketpair_with_real_socket(*args, **kwargs):
    guarded_socket_class = _socket_module.socket
    _socket_module.socket = _real_socket_class
    try:
        return _original_socketpair(*args, **kwargs)
    finally:
        _socket_module.socket = guarded_socket_class


_socket_module.socketpair = _socketpair_with_real_socket


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/ loadable by every test in this suite."""
    yield


@pytest.fixture
async def linked_setup(hass: HomeAssistant, mqtt_mock):
    """Set up the integration plus a pre-existing HA device for IEEE_ADDRESS.

    Simulates the scenario this integration is built around: Zigbee2MQTT's
    own MQTT discovery has already created an HA device for this Zigbee
    device (here, a bare mqtt config entry + a device registered with the
    identifier convention device_link.py looks for), and Zigbee2MQTT reports
    it via bridge/devices. Returns (entry, target_device).
    """
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    registry = dr.async_get(hass)
    target_device = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zigbee2mqtt",
        data={CONF_NAME: "Test Instance", CONF_BASE_TOPIC: "zigbee2mqtt"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    return entry, target_device
