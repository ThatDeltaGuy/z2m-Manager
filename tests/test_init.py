"""End-to-end tests for setting up and unloading a config entry.

Both tests mark expected_lingering_timers=True: the shared mqtt_mock fixture
wraps a real MQTT client whose internal keep-alive periodic task isn't fully
torn down by the test harness's hass teardown. That's an artifact of the mock
itself (used unchanged from upstream HA's own test conventions), not of this
integration's setup/unload code - test_unload_entry_unsubscribes still
asserts our own hub state (subscriptions, pending requests) is cleaned up.
"""

from __future__ import annotations

import json

import pytest
from homeassistant.config_entries import ConfigEntryState
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
async def test_setup_entry_succeeds_and_subscribes(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    assert config_entry.state is ConfigEntryState.LOADED

    hub = config_entry.runtime_data
    assert hub is not None

    async_fire_mqtt_message(
        hass, "zigbee2mqtt/bridge/info", json.dumps({"version": "1.40.0", "log_level": "info"})
    )
    await hass.async_block_till_done()

    assert hub.bridge_info is not None
    assert hub.bridge_info.version == "1.40.0"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_unload_entry_unsubscribes(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hub = config_entry.runtime_data

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert hub._pending == {}

    # A message arriving after unload must not be processed (no subscribers left).
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/info", json.dumps({"version": "9.9.9"}))
    await hass.async_block_till_done()
    assert hub.bridge_info is None
