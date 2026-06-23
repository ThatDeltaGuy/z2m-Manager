"""Tests for the options flow and that changes apply live without a reload."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zigbee2mqtt_manager.const import (
    CONF_BASE_TOPIC,
    CONF_BATTERY_LOW_THRESHOLD_PERCENT,
    CONF_LOW_LQI_THRESHOLD,
    CONF_NAME,
    CONF_NETWORKMAP_INTERVAL_MINUTES,
    CONF_NETWORKMAP_ROUTES,
    CONF_NETWORKMAP_TYPE,
    CONF_OFFLINE_THRESHOLD_MINUTES,
    CONF_OTA_CHECK_INTERVAL_MINUTES,
    CONF_PERMIT_JOIN_DURATION,
    DOMAIN,
)


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
async def test_options_flow_updates_hub_live(
    hass: HomeAssistant, mqtt_mock, config_entry: MockConfigEntry
) -> None:
    hub = config_entry.runtime_data
    assert hub.offline_threshold_minutes == 15  # default, before any options set

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_OFFLINE_THRESHOLD_MINUTES: 60,
            CONF_NETWORKMAP_INTERVAL_MINUTES: 30,
            CONF_NETWORKMAP_TYPE: "graphviz",
            CONF_NETWORKMAP_ROUTES: True,
            CONF_PERMIT_JOIN_DURATION: 120,
            CONF_BATTERY_LOW_THRESHOLD_PERCENT: 25,
            CONF_LOW_LQI_THRESHOLD: 70,
            CONF_OTA_CHECK_INTERVAL_MINUTES: 720,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY

    # No reload happened (the entry stays loaded) - the listener applied the
    # new values to the *same* hub object directly.
    assert config_entry.runtime_data is hub
    assert hub.offline_threshold_minutes == 60
    assert hub.networkmap_type == "graphviz"
    assert hub.networkmap_routes is True
    assert hub.permit_join_duration == 120
    assert hub.battery_low_threshold_percent == 25
    assert hub.low_lqi_threshold == 70
    assert hub._networkmap_interval_minutes == 30
    assert hub._networkmap_timer_unsub is not None
    assert hub._ota_check_interval_minutes == 720
    assert hub._ota_check_timer_unsub is not None

    hub._reschedule_networkmap_timer(0)  # cleanup so no real timers linger past the test
    hub._reschedule_ota_check_timer(0)
