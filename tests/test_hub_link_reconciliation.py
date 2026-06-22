"""Tests for Z2MHub's debounced device-link reconciliation.

async_call_later (used for debouncing) schedules via the raw asyncio loop
clock, not HA's fake-time-event helpers, so these tests use a real short
sleep past LINK_RECONCILE_DEBOUNCE rather than async_fire_time_changed.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import (
    LINK_RECONCILE_DEBOUNCE,
    signal_device_linkable,
    signal_device_unlinkable,
)
from custom_components.zigbee2mqtt_manager.hub import Z2MHub

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"
IEEE_ADDRESS = "0x00124b0023d4f1a2"
FRIENDLY_NAME = "living_room_light"

# Comfortably past LINK_RECONCILE_DEBOUNCE (0.5s).
SETTLE_SECONDS = LINK_RECONCILE_DEBOUNCE + 0.2


def _bridge_devices_msg(ieee_address: str, friendly_name: str) -> list[dict]:
    return [{"ieee_address": ieee_address, "friendly_name": friendly_name}]


@pytest.fixture
async def hub(hass: HomeAssistant, mqtt_mock) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    await instance.async_setup()
    await asyncio.sleep(0.6)  # let the MQTT subscribe debouncer's cooldown elapse
    yield instance
    await instance.async_unload()


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_device_becomes_linkable_fires_signal(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)
    hub._mqtt_config_entry_id = mqtt_entry.entry_id

    registry = dr.async_get(hass)
    target_device = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    payloads = []
    async_dispatcher_connect(hass, signal_device_linkable(ENTRY_ID), lambda payload: payloads.append(payload))

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/devices",
        json.dumps(_bridge_devices_msg(IEEE_ADDRESS, FRIENDLY_NAME)),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    assert len(payloads) == 1
    assert payloads[0].ieee_address == IEEE_ADDRESS
    assert payloads[0].ha_device_id == target_device.id
    assert hub.device_id_to_ieee[target_device.id] == IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_unchanged_device_does_not_resignal(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)
    hub._mqtt_config_entry_id = mqtt_entry.entry_id

    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    payloads = []
    async_dispatcher_connect(hass, signal_device_linkable(ENTRY_ID), lambda payload: payloads.append(payload))

    msg = json.dumps(_bridge_devices_msg(IEEE_ADDRESS, FRIENDLY_NAME))
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", msg)
    await asyncio.sleep(SETTLE_SECONDS)
    assert len(payloads) == 1

    # Republish the identical device list (Z2M does this on every join/leave
    # elsewhere on the network, not just for this device) - must not resignal.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", msg)
    await asyncio.sleep(SETTLE_SECONDS)
    assert len(payloads) == 1


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_device_becomes_unlinkable_when_ha_device_removed(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)
    hub._mqtt_config_entry_id = mqtt_entry.entry_id

    registry = dr.async_get(hass)
    target_device = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    msg = json.dumps(_bridge_devices_msg(IEEE_ADDRESS, FRIENDLY_NAME))
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", msg)
    await asyncio.sleep(SETTLE_SECONDS)
    assert hub.device_id_to_ieee[target_device.id] == IEEE_ADDRESS

    unlinked = []
    async_dispatcher_connect(hass, signal_device_unlinkable(ENTRY_ID), lambda ieee: unlinked.append(ieee))

    registry.async_remove_device(target_device.id)
    # Removing the HA device doesn't itself trigger our hub - re-publish
    # bridge/devices (as Z2M would on its own periodic basis) to force
    # re-resolution; the device is still on the Zigbee network, just no
    # longer linkable in HA.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", msg)
    await asyncio.sleep(SETTLE_SECONDS)

    assert unlinked == [IEEE_ADDRESS]
    assert target_device.id not in hub.device_id_to_ieee


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_device_removed_from_bridge_devices_unlinks(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)
    hub._mqtt_config_entry_id = mqtt_entry.entry_id

    registry = dr.async_get(hass)
    target_device = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/devices",
        json.dumps(_bridge_devices_msg(IEEE_ADDRESS, FRIENDLY_NAME)),
    )
    await asyncio.sleep(SETTLE_SECONDS)
    assert IEEE_ADDRESS in hub._link_cache

    unlinked = []
    async_dispatcher_connect(hass, signal_device_unlinkable(ENTRY_ID), lambda ieee: unlinked.append(ieee))

    # Z2M un-paired the device entirely - bridge/devices no longer lists it.
    async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", json.dumps([]))
    await asyncio.sleep(SETTLE_SECONDS)

    assert unlinked == [IEEE_ADDRESS]
    assert IEEE_ADDRESS not in hub._link_cache
    assert target_device.id not in hub.device_id_to_ieee


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_rapid_republishes_are_debounced_into_one_reconciliation(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)
    hub._mqtt_config_entry_id = mqtt_entry.entry_id

    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    payloads = []
    async_dispatcher_connect(hass, signal_device_linkable(ENTRY_ID), lambda payload: payloads.append(payload))

    msg = json.dumps(_bridge_devices_msg(IEEE_ADDRESS, FRIENDLY_NAME))
    # Five republishes in quick succession (well inside the debounce window).
    for _ in range(5):
        async_fire_mqtt_message(hass, f"{BASE_TOPIC}/bridge/devices", msg)
    await asyncio.sleep(SETTLE_SECONDS)

    assert len(payloads) == 1
