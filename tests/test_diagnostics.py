"""Tests for config entry diagnostics."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.zigbee2mqtt_manager.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_diagnostics_includes_device_linking_state(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, target_device = linked_setup

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["base_topic"] == "zigbee2mqtt"
    assert diagnostics["devices"]["count"] == 1
    assert diagnostics["devices"]["devices"][0]["ieee_address"] == IEEE_ADDRESS
    assert diagnostics["device_linking"]["link_cache"][IEEE_ADDRESS]["ha_device_id"] == target_device.id
    assert diagnostics["device_linking"]["device_id_to_ieee"][target_device.id] == IEEE_ADDRESS
    assert diagnostics["pending_requests"] == 0
    assert diagnostics["networkmap"] is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_diagnostics_handles_no_bridge_info_yet(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    """bridge/info and bridge/devices arrive independently - must not assume one implies the other."""
    entry, _target_device = linked_setup

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["bridge"]["info"] is None
