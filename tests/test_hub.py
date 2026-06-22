"""Tests for Z2MHub's MQTT message parsing."""

from __future__ import annotations

import json

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.zigbee2mqtt_manager.const import (
    signal_bridge_groups,
    signal_bridge_info,
    signal_bridge_state,
    signal_devices,
)
from custom_components.zigbee2mqtt_manager.hub import Z2MHub

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


def _msg(topic: str, payload: str) -> ReceiveMessage:
    return ReceiveMessage(
        topic=topic,
        payload=payload,
        qos=0,
        retain=True,
        subscribed_topic=topic,
        timestamp=0.0,
    )


@pytest.fixture
async def hub(hass: HomeAssistant) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    yield instance
    # _handle_bridge_devices can schedule a debounced link-reconciliation
    # timer; unload cancels it so it doesn't linger past the test.
    await instance.async_unload()


async def test_handle_bridge_info_parses_and_dispatches(hass: HomeAssistant, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(hass, signal_bridge_info(ENTRY_ID), lambda info: received.append(info))

    payload = {
        "version": "1.40.0",
        "coordinator": {"ieee_address": "0x00124b0023d4f1a2"},
        "network": {"channel": 15, "pan_id": "0x1a2b"},
        "log_level": "info",
        "permit_join": True,
        "permit_join_end": 1234567890,
    }
    hub._handle_bridge_info(_msg(f"{BASE_TOPIC}/bridge/info", json.dumps(payload)))
    await hass.async_block_till_done()

    assert hub.bridge_info is not None
    assert hub.bridge_info.version == "1.40.0"
    assert hub.bridge_info.log_level == "info"
    assert hub.bridge_info.permit_join is True
    assert hub.bridge_info.network["channel"] == 15
    assert len(received) == 1
    assert received[0] is hub.bridge_info


async def test_handle_bridge_state_json(hass: HomeAssistant, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(hass, signal_bridge_state(ENTRY_ID), lambda online: received.append(online))

    hub._handle_bridge_state(_msg(f"{BASE_TOPIC}/bridge/state", json.dumps({"state": "online"})))
    await hass.async_block_till_done()

    assert hub.bridge_online is True
    assert received == [True]

    hub._handle_bridge_state(_msg(f"{BASE_TOPIC}/bridge/state", json.dumps({"state": "offline"})))
    await hass.async_block_till_done()

    assert hub.bridge_online is False
    assert received == [True, False]


async def test_handle_bridge_state_plain_text_fallback(hass: HomeAssistant, hub: Z2MHub) -> None:
    """Older Zigbee2MQTT versions publish bare 'online'/'offline', not JSON."""
    hub._handle_bridge_state(_msg(f"{BASE_TOPIC}/bridge/state", "online"))
    await hass.async_block_till_done()

    assert hub.bridge_online is True


async def test_handle_bridge_devices(hass: HomeAssistant, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(hass, signal_devices(ENTRY_ID), lambda devices: received.append(devices))

    payload = [
        {
            "ieee_address": "0x000d6ffffe9d363c",
            "friendly_name": "living_room_light",
            "type": "Router",
            "model_id": "LCT001",
            "software_build_id": "1.2.3",
            "supported": True,
            "disabled": False,
            "interview_completed": True,
        },
        {
            "ieee_address": "0x00158d00018255df",
            "friendly_name": "hallway_motion",
            "type": "EndDevice",
        },
    ]
    hub._handle_bridge_devices(_msg(f"{BASE_TOPIC}/bridge/devices", json.dumps(payload)))
    await hass.async_block_till_done()

    assert len(hub.devices) == 2
    light = hub.devices["0x000d6ffffe9d363c"]
    assert light.friendly_name == "living_room_light"
    assert light.software_build_id == "1.2.3"
    assert hub.devices["0x00158d00018255df"].friendly_name == "hallway_motion"
    assert len(received) == 1
    assert received[0] is hub.devices


async def test_handle_bridge_devices_skips_entries_without_ieee_address(
    hass: HomeAssistant, hub: Z2MHub
) -> None:
    payload = [{"friendly_name": "broken_entry"}]
    hub._handle_bridge_devices(_msg(f"{BASE_TOPIC}/bridge/devices", json.dumps(payload)))
    await hass.async_block_till_done()

    assert hub.devices == {}


async def test_handle_bridge_groups(hass: HomeAssistant, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(hass, signal_bridge_groups(ENTRY_ID), lambda groups: received.append(groups))

    payload = [{"id": 1, "friendly_name": "downstairs_lights", "members": [{"device": "x"}]}]
    hub._handle_bridge_groups(_msg(f"{BASE_TOPIC}/bridge/groups", json.dumps(payload)))
    await hass.async_block_till_done()

    assert hub.groups[1].friendly_name == "downstairs_lights"
    assert len(received) == 1


async def test_handle_bridge_response_resolves_pending_future(hass: HomeAssistant, hub: Z2MHub) -> None:
    future = hass.loop.create_future()
    hub._pending[("permit_join", "tx-1")] = future

    response = {"data": {"time": 254}, "status": "ok", "transaction": "tx-1"}
    hub._handle_bridge_response(_msg(f"{BASE_TOPIC}/bridge/response/permit_join", json.dumps(response)))

    assert future.done()
    assert future.result() == response


async def test_handle_bridge_response_with_nested_command_name(hass: HomeAssistant, hub: Z2MHub) -> None:
    """Commands like 'device/remove' contain a slash - must not be split naively."""
    future = hass.loop.create_future()
    hub._pending[("device/remove", "tx-2")] = future

    response = {"data": {"id": "my_bulb"}, "status": "ok", "transaction": "tx-2"}
    hub._handle_bridge_response(_msg(f"{BASE_TOPIC}/bridge/response/device/remove", json.dumps(response)))

    assert future.done()
    assert future.result()["data"]["id"] == "my_bulb"


async def test_handle_bridge_response_discards_unmatched(hass: HomeAssistant, hub: Z2MHub) -> None:
    """A response with no matching pending future must not raise."""
    response = {"data": {}, "status": "ok", "transaction": "unknown-tx"}
    hub._handle_bridge_response(_msg(f"{BASE_TOPIC}/bridge/response/restart", json.dumps(response)))
    # No assertion needed beyond "did not raise" - this is the expected/common case.


async def test_async_unload_cancels_pending_futures(hass: HomeAssistant, hub: Z2MHub) -> None:
    future = hass.loop.create_future()
    hub._pending[("restart", "tx-3")] = future
    hub._unsubscribes = [lambda: None]

    await hub.async_unload()

    assert future.cancelled()
    assert hub._pending == {}
