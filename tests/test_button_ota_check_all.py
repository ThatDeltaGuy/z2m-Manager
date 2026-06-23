"""Tests for the bridge-level "check for firmware updates" (OTA check all) button.

Z2MHub.async_check_all_ota_updates itself is already covered thoroughly in
test_hub_ota_check.py (concurrency, coordinator exclusion, per-device
failure isolation) - this file only checks the button entity wires up to it.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN

from .helpers import PUBLISH_SETTLE_SECONDS

ENTITY_ID = "button.test_instance_check_for_firmware_updates"


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
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {"ieee_address": "0xAAA", "friendly_name": "device_a"},
                {"ieee_address": "0xBBB", "friendly_name": "device_b"},
            ]
        ),
    )
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_press_checks_every_device(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": ENTITY_ID}))
    await asyncio.sleep(PUBLISH_SETTLE_SECONDS)

    topic = "zigbee2mqtt/bridge/request/device/ota_update/check"
    checked_ids = {
        json.loads(call.args[1])["id"] for call in mqtt_mock.async_publish.mock_calls if call.args[0] == topic
    }
    assert checked_ids == {"0xAAA", "0xBBB"}

    # Answer both so nothing lingers past the test.
    for call in list(mqtt_mock.async_publish.mock_calls):
        if call.args[0] != topic:
            continue
        payload = json.loads(call.args[1])
        async_fire_mqtt_message(
            hass,
            "zigbee2mqtt/bridge/response/device/ota_update/check",
            json.dumps(
                {
                    "data": {"update_available": False},
                    "status": "ok",
                    "transaction": payload["transaction"],
                }
            ),
        )
    await hass.async_block_till_done()


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_button_unavailable_when_bridge_offline(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "offline"}))
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "unavailable"
