"""Tests for the bridge connectivity binary sensor."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN


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
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_connectivity_sensor_reflects_bridge_state(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    entity_id = "binary_sensor.test_instance_connectivity"

    assert hass.states.get(entity_id).state == "off"

    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"

    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "offline"}))
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_connectivity_sensor_stays_available_when_bridge_offline(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    entity_id = "binary_sensor.test_instance_connectivity"

    # Never reported online: the connectivity sensor must still show a real
    # off state, not "unavailable" - it would defeat its own purpose otherwise.
    state = hass.states.get(entity_id)
    assert state.state == "off"
