"""End-to-end tests for per-device extras (remove/re-interview buttons).

Covers the milestone's core requirements: entities only appear once a device
is linkable to an existing HA device, they attach to that device (not a
duplicate), and they disappear again the moment the device stops being
linkable - without restarting HA. Also covers that both buttons are
disabled in the entity registry by default (so they can't be pressed by
accident from a dashboard), and that the options flow can flip either back
on for newly-linked devices.

There is deliberately no per-device OTA update entity here: Zigbee2MQTT's
own MQTT discovery already provides one, so adding our own would be exactly
the duplication this integration is built to avoid. OTA is still reachable
via the bridge-level OTA-available sensor, the check-all-devices button, and
the ota_check/ota_update services (see test_hub_device_metrics.py,
test_button_ota_check_all.py, and test_services.py).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_mqtt_message,
)

from custom_components.zigbee2mqtt_manager.const import (
    CONF_BASE_TOPIC,
    CONF_NAME,
    CONF_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT,
    CONF_REMOVE_BUTTON_ENABLED_BY_DEFAULT,
    DOMAIN,
)

from .conftest import FRIENDLY_NAME, IEEE_ADDRESS, SETTLE_SECONDS
from .helpers import async_respond_ok

REMOVE_ENTITY_ID = "button.living_room_light_remove_device"
REINTERVIEW_ENTITY_ID = "button.living_room_light_re_interview"


@pytest.fixture
async def linked_setup_buttons_enabled(hass: HomeAssistant, mqtt_mock):
    """Like conftest.py's linked_setup, but with both buttons enabled by
    default from the start - needed for tests that actually press them,
    since flipping disabled_by on an existing registry entry doesn't bring
    a live entity to life within a single test run the way a real HA
    restart/reload would.
    """
    mqtt_entry = MockConfigEntry(domain="mqtt")
    mqtt_entry.add_to_hass(hass)

    registry = dr.async_get(hass)
    target_device = registry.async_get_or_create(
        config_entry_id=mqtt_entry.entry_id,
        identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")},
        name=FRIENDLY_NAME,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zigbee2mqtt",
        data={CONF_NAME: "Test Instance", CONF_BASE_TOPIC: "zigbee2mqtt"},
        options={
            CONF_REMOVE_BUTTON_ENABLED_BY_DEFAULT: True,
            CONF_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT: True,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, "zigbee2mqtt/bridge/state", json.dumps({"state": "online"}))
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    return entry, target_device


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_per_device_entities_appear_and_attach_to_existing_device(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    """Checks the entity *registry*, not hass.states: both buttons are
    disabled by default (see test_buttons_disabled_by_default below), so
    they correctly have no state - that must not be mistaken for "not
    created" or "not attached".
    """
    _entry, target_device = linked_setup

    registry = er.async_get(hass)
    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        entry = registry.async_get(entity_id)
        assert entry is not None, f"{entity_id} was not created"
        assert entry.device_id == target_device.id, (
            f"{entity_id} attached to {entry.device_id}, expected the existing "
            f"device {target_device.id} (must not be a duplicate device)"
        )

    # Confirm it really is the same device as the one originally created,
    # not a same-id coincidence: device registry should still only have one
    # entry for this ieee_address's identifier.
    device_registry = dr.async_get(hass)
    assert (
        device_registry.async_get_device(identifiers={("mqtt", f"zigbee2mqtt_{IEEE_ADDRESS}")}).id
        == target_device.id
    )


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_buttons_disabled_by_default(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    """Neither button can be pressed by accident from a dashboard out of the box."""
    registry = er.async_get(hass)
    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        entry = registry.async_get(entity_id)
        assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_buttons_enabled_by_default_when_configured(
    hass: HomeAssistant, mqtt_mock, linked_setup_buttons_enabled
) -> None:
    registry = er.async_get(hass)
    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        entry = registry.async_get(entity_id)
        assert entry.disabled_by is None
        assert hass.states.get(entity_id) is not None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_devices_without_ha_discovery_get_no_per_device_entities(
    hass: HomeAssistant, mqtt_mock
) -> None:
    """The project's explicit decision: skip extras entirely, never create a fallback device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="zigbee2mqtt",
        data={CONF_NAME: "Test Instance", CONF_BASE_TOPIC: "zigbee2mqtt"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    registry = er.async_get(hass)
    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        assert registry.async_get(entity_id) is None

    # The config entry's own bridge-level device (for the restart button
    # etc.) is expected and always exists - what must NOT exist is a second,
    # fallback device standing in for the unlinked Zigbee device.
    device_registry = dr.async_get(hass)
    matching = [
        device for device in device_registry.devices.values() if entry.entry_id in device.config_entries
    ]
    assert len(matching) == 1
    assert matching[0].model == "Bridge"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_entities_disappear_when_device_becomes_unlinkable(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, target_device = linked_setup
    registry = er.async_get(hass)
    assert registry.async_get(REMOVE_ENTITY_ID) is not None

    dr.async_get(hass).async_remove_device(target_device.id)
    # Force re-resolution, mirroring a periodic bridge/devices republish.
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        assert registry.async_get(entity_id) is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_enabled_entities_disappear_when_device_becomes_unlinkable(
    hass: HomeAssistant, mqtt_mock, linked_setup_buttons_enabled
) -> None:
    _entry, target_device = linked_setup_buttons_enabled
    registry = er.async_get(hass)
    assert registry.async_get(REMOVE_ENTITY_ID) is not None

    dr.async_get(hass).async_remove_device(target_device.id)
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    for entity_id in (REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        assert registry.async_get(entity_id) is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_remove_button_publishes_soft_remove(
    hass: HomeAssistant, mqtt_mock, linked_setup_buttons_enabled
) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": REMOVE_ENTITY_ID}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/remove", data={"id": IEEE_ADDRESS})
    assert sent == {
        "id": IEEE_ADDRESS,
        "force": False,
        "block": False,
        "transaction": sent["transaction"],
    }


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_reinterview_button_publishes_request(
    hass: HomeAssistant, mqtt_mock, linked_setup_buttons_enabled
) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": REINTERVIEW_ENTITY_ID}))
    sent = await async_respond_ok(
        hass, mqtt_mock, "zigbee2mqtt", "device/interview", data={"id": IEEE_ADDRESS}
    )
    assert sent["id"] == IEEE_ADDRESS
