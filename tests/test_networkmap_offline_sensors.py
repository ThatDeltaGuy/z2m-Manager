"""End-to-end tests for the network map sensor, offline devices sensor, and
the network-map refresh button.
"""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN

from .helpers import async_respond_ok

NETWORKMAP_ENTITY_ID = "sensor.test_instance_network_map"
OFFLINE_ENTITY_ID = "sensor.test_instance_offline_devices"
BATTERY_LOW_ENTITY_ID = "sensor.test_instance_battery_low_devices"
LOW_LQI_ENTITY_ID = "sensor.test_instance_low_link_quality_devices"
OTA_AVAILABLE_ENTITY_ID = "sensor.test_instance_firmware_updates_available"
REFRESH_BUTTON_ENTITY_ID = "button.test_instance_refresh_network_map"


@pytest.fixture
async def config_entry(hass: HomeAssistant, mqtt_mock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zigbee2mqtt",
        data={CONF_NAME: "Test Instance", CONF_BASE_TOPIC: "zigbee2mqtt"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_networkmap_sensor_state_and_attributes_after_refresh(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    assert hass.states.get(NETWORKMAP_ENTITY_ID).state == "unknown"

    hass.async_create_task(
        hass.services.async_call("button", "press", {"entity_id": REFRESH_BUTTON_ENTITY_ID})
    )
    await async_respond_ok(
        hass,
        mqtt_mock,
        "zigbee2mqtt",
        "networkmap",
        data={"type": "raw", "value": {"nodes": [{"ieeeAddr": "0xAAA"}], "links": []}},
    )

    state = hass.states.get(NETWORKMAP_ENTITY_ID)
    assert state.state != "unknown"
    assert state.attributes["type"] == "raw"
    assert state.attributes["value"] == {"nodes": [{"ieeeAddr": "0xAAA"}], "links": []}
    # nodes/links are also spread as top-level attributes (not just nested
    # under "value") to match the long-standing community MQTT-template-
    # sensor convention that existing Lovelace network-map cards expect.
    assert state.attributes["nodes"] == [{"ieeeAddr": "0xAAA"}]
    assert state.attributes["links"] == []


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_offline_devices_sensor_counts_and_lists(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {"ieee_address": "0xAAA", "friendly_name": "kitchen_light"},
                {"ieee_address": "0xBBB", "friendly_name": "hallway_sensor"},
            ]
        ),
    )
    await hass.async_block_till_done()

    assert hass.states.get(OFFLINE_ENTITY_ID).state == "0"

    async_fire_mqtt_message(hass, "zigbee2mqtt/kitchen_light/availability", json.dumps({"state": "offline"}))
    await hass.async_block_till_done()

    state = hass.states.get(OFFLINE_ENTITY_ID)
    assert state.state == "1"
    assert len(state.attributes["devices"]) == 1
    assert state.attributes["devices"][0]["name"] == "kitchen_light"
    assert "last_seen" in state.attributes["devices"][0]
    assert set(state.attributes["devices"][0]) == {"name", "last_seen"}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_battery_low_devices_sensor_counts_and_lists(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {"ieee_address": "0xAAA", "friendly_name": "kitchen_light"},
                {"ieee_address": "0xCOORD", "friendly_name": "Coordinator", "type": "Coordinator"},
            ]
        ),
    )
    await hass.async_block_till_done()

    assert hass.states.get(BATTERY_LOW_ENTITY_ID).state == "0"

    async_fire_mqtt_message(hass, "zigbee2mqtt/kitchen_light", json.dumps({"battery": 10}))
    await hass.async_block_till_done()

    state = hass.states.get(BATTERY_LOW_ENTITY_ID)
    assert state.state == "1"
    assert state.attributes["devices"] == [{"name": "kitchen_light", "battery": 10}]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_low_lqi_devices_sensor_counts_and_lists(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": "0xAAA", "friendly_name": "kitchen_light"}]),
    )
    await hass.async_block_till_done()

    assert hass.states.get(LOW_LQI_ENTITY_ID).state == "0"

    async_fire_mqtt_message(hass, "zigbee2mqtt/kitchen_light", json.dumps({"linkquality": 20}))
    await hass.async_block_till_done()

    state = hass.states.get(LOW_LQI_ENTITY_ID)
    assert state.state == "1"
    assert state.attributes["devices"] == [{"name": "kitchen_light", "linkquality": 20}]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_ota_available_devices_sensor_counts_and_lists(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": "0xAAA", "friendly_name": "kitchen_light"}]),
    )
    await hass.async_block_till_done()

    assert hass.states.get(OTA_AVAILABLE_ENTITY_ID).state == "0"

    async_fire_mqtt_message(hass, "zigbee2mqtt/kitchen_light", json.dumps({"update": {"state": "available"}}))
    await hass.async_block_till_done()

    state = hass.states.get(OTA_AVAILABLE_ENTITY_ID)
    assert state.state == "1"
    assert state.attributes["devices"] == [{"name": "kitchen_light"}]
