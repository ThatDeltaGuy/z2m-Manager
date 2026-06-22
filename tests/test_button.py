"""Tests for the restart button."""

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

ENTITY_ID = "button.test_instance_restart"


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
async def test_press_publishes_restart_request(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": ENTITY_ID}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "restart")
    assert "transaction" in sent


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_button_unavailable_when_bridge_offline(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "offline"}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "unavailable"
