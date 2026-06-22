"""Tests for the permit-join switch."""

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

ENTITY_ID = "switch.test_instance_permit_join"


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
async def test_switch_reflects_permit_join_state(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    assert hass.states.get(ENTITY_ID).state == "off"

    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/info", json.dumps({"permit_join": True}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "on"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_switch_turn_on_publishes_configured_duration(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hass.async_create_task(hass.services.async_call("switch", "turn_on", {"entity_id": ENTITY_ID}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "permit_join")
    assert sent["time"] == 254  # DEFAULT_PERMIT_JOIN_DURATION


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_switch_turn_off_publishes_zero(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hass.async_create_task(hass.services.async_call("switch", "turn_off", {"entity_id": ENTITY_ID}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "permit_join")
    assert sent["time"] == 0
