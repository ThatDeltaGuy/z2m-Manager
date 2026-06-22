"""Tests for the bridge info sensor."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN

ENTITY_ID = "sensor.test_instance_bridge_info"


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

    # Bridge entities (other than the connectivity sensor itself) report
    # unavailable until a bridge/state message is seen - bring the bridge
    # online here so attribute assertions below have something to check.
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bridge_info_sensor_state_and_attributes(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    assert hass.states.get(ENTITY_ID).state == "unknown"

    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/info",
        json.dumps(
            {
                "version": "1.40.0",
                "coordinator": {"ieee_address": "0x00124b0023d4f1a2"},
                "network": {"channel": 15, "pan_id": "0x1a2b"},
                "log_level": "info",
                "permit_join": True,
                "permit_join_end": 1234567890,
            }
        ),
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == "1.40.0"
    assert state.attributes["channel"] == 15
    assert state.attributes["pan_id"] == "0x1a2b"
    assert state.attributes["log_level"] == "info"
    assert state.attributes["permit_join"] is True
    assert state.attributes["groups"] == []


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bridge_info_sensor_includes_groups(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/groups",
        json.dumps([{"id": 1, "friendly_name": "downstairs_lights", "members": []}]),
    )
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes["groups"] == ["downstairs_lights"]
