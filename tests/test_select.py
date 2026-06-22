"""Tests for the log level select."""

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

ENTITY_ID = "select.test_instance_log_level"


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
async def test_select_reflects_log_level(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/info", json.dumps({"log_level": "warning"}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "warning"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_select_option_publishes_nested_options(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hass.async_create_task(
        hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": ENTITY_ID, "option": "debug"},
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "options", data={"restart_required": False})
    assert sent["options"] == {"advanced": {"log_level": "debug"}}
