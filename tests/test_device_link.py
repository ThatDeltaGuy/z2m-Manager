"""Tests for the device-linking lookup module.

These are the most valuable tests in the project given the explicitly-flagged
uncertainty around Strategy 1's exact identifier string: only the first test
below depends on that string being correct. The friendly_name-fallback and
not-found cases are independent of it, so this module's contract is pinned
regardless of whether Strategy 1 needs correcting later.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zigbee2mqtt_manager.device_link import (
    async_get_mqtt_config_entry_id,
    find_ha_device_for_z2m_device,
)

IEEE_ADDRESS = "0x00124b0023d4f1a2"
FRIENDLY_NAME = "living_room_light"


async def test_strategy_1_matches_by_reconstructed_identifier(hass: HomeAssistant) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    registry = dr.async_get(hass)
    created = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name="Some Other Name",  # deliberately not friendly_name - identifier match shouldn't need it
    )

    result = find_ha_device_for_z2m_device(
        hass,
        ieee_address=IEEE_ADDRESS,
        friendly_name=FRIENDLY_NAME,
        mqtt_config_entry_id=mqtt_entry.entry_id,
    )

    assert result.method == "identifier"
    assert result.ha_device_id == created.id


async def test_strategy_2_falls_back_to_friendly_name_match(hass: HomeAssistant) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    registry = dr.async_get(hass)
    created = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", "some_unrelated_identifier")},
        name=FRIENDLY_NAME,
    )

    result = find_ha_device_for_z2m_device(
        hass,
        ieee_address=IEEE_ADDRESS,
        friendly_name=FRIENDLY_NAME,
        mqtt_config_entry_id=mqtt_entry.entry_id,
    )

    assert result.method == "friendly_name"
    assert result.ha_device_id == created.id


async def test_strategy_2_matches_user_renamed_device(hass: HomeAssistant) -> None:
    """name_by_user (a user rename in HA) must also be checked, not just name."""
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    registry = dr.async_get(hass)
    created = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", "some_unrelated_identifier")},
        name="Original Z2M Name",
    )
    registry.async_update_device(created.id, name_by_user=FRIENDLY_NAME)

    result = find_ha_device_for_z2m_device(
        hass,
        ieee_address=IEEE_ADDRESS,
        friendly_name=FRIENDLY_NAME,
        mqtt_config_entry_id=mqtt_entry.entry_id,
    )

    assert result.method == "friendly_name"
    assert result.ha_device_id == created.id


async def test_not_found_when_neither_strategy_matches(hass: HomeAssistant) -> None:
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    result = find_ha_device_for_z2m_device(
        hass,
        ieee_address=IEEE_ADDRESS,
        friendly_name=FRIENDLY_NAME,
        mqtt_config_entry_id=mqtt_entry.entry_id,
    )

    assert result.ha_device_id is None
    assert result.method == "not_found"


async def test_not_found_skips_strategy_2_when_no_mqtt_entry_id(hass: HomeAssistant) -> None:
    """Strategy 2 needs a single mqtt config entry id; None must not raise."""
    result = find_ha_device_for_z2m_device(
        hass,
        ieee_address=IEEE_ADDRESS,
        friendly_name=FRIENDLY_NAME,
        mqtt_config_entry_id=None,
    )

    assert result.ha_device_id is None
    assert result.method == "not_found"


async def test_find_function_never_creates_a_device(hass: HomeAssistant) -> None:
    """Read-only by construction: a lookup miss must not add a registry entry."""
    registry = dr.async_get(hass)
    before = len(registry.devices)

    find_ha_device_for_z2m_device(
        hass, ieee_address=IEEE_ADDRESS, friendly_name=FRIENDLY_NAME, mqtt_config_entry_id=None
    )

    assert len(registry.devices) == before


async def test_async_get_mqtt_config_entry_id_with_exactly_one_entry(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(domain="mqtt")
    entry.add_to_hass(hass)

    assert async_get_mqtt_config_entry_id(hass) == entry.entry_id


async def test_async_get_mqtt_config_entry_id_with_zero_entries(hass: HomeAssistant) -> None:
    assert async_get_mqtt_config_entry_id(hass) is None


async def test_async_get_mqtt_config_entry_id_with_multiple_entries(
    hass: HomeAssistant,
) -> None:
    MockConfigEntry(domain="mqtt").add_to_hass(hass)
    MockConfigEntry(domain="mqtt").add_to_hass(hass)

    assert async_get_mqtt_config_entry_id(hass) is None
