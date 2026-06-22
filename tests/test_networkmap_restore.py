"""Test that the network map sensor restores across a simulated HA restart."""

from __future__ import annotations

import json

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
    mock_restore_cache_with_extra_data,
)

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN

ENTITY_ID = "sensor.test_instance_network_map"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_networkmap_sensor_restores_after_restart(hass: HomeAssistant, mqtt_mock) -> None:
    restored_timestamp = dt_util.utcnow().replace(microsecond=0)
    restored_value = {"nodes": [{"ieeeAddr": "0xAAA"}], "links": []}

    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY_ID, restored_timestamp.isoformat()),
                {
                    "native_value": {
                        "__type": "<class 'datetime.datetime'>",
                        "isoformat": restored_timestamp.isoformat(),
                    },
                    "native_unit_of_measurement": None,
                    "networkmap_type": "raw",
                    "value": restored_value,
                },
            )
        ],
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zigbee2mqtt",
        data={CONF_NAME: "Test Instance", CONF_BASE_TOPIC: "zigbee2mqtt"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Bridge-level sensors are unavailable until the bridge is known online
    # (see Z2MBridgeEntity.available) - bring it online to actually see the
    # restored value, mirroring real startup where bridge/state always
    # arrives shortly after Zigbee2MQTT itself starts.
    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert dt_util.parse_datetime(state.state) == restored_timestamp
    assert state.attributes["type"] == "raw"
    assert state.attributes["value"] == restored_value

    # The hub's own state was populated too, not just the entity's displayed
    # state - e.g. a future refresh/service call reading hub.last_networkmap
    # directly would see the restored data, not None.
    assert entry.runtime_data.last_networkmap is not None
    assert entry.runtime_data.last_networkmap.value == restored_value
