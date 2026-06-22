"""End-to-end tests for per-device extras (OTA update, remove/re-interview buttons).

Covers the milestone's core requirements: entities only appear once a device
is linkable to an existing HA device, they attach to that device (not a
duplicate), and they disappear again the moment the device stops being
linkable - without restarting HA.
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

from custom_components.zigbee2mqtt_manager.const import CONF_BASE_TOPIC, CONF_NAME, DOMAIN

from .conftest import FRIENDLY_NAME, IEEE_ADDRESS, SETTLE_SECONDS
from .helpers import async_respond_ok

UPDATE_ENTITY_ID = "update.living_room_light_firmware"
REMOVE_ENTITY_ID = "button.living_room_light_remove_device"
REINTERVIEW_ENTITY_ID = "button.living_room_light_re_interview"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_per_device_entities_appear_and_attach_to_existing_device(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, target_device = linked_setup

    for entity_id in (UPDATE_ENTITY_ID, REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} was not created"

    registry = er.async_get(hass)
    for entity_id in (UPDATE_ENTITY_ID, REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        entry = registry.async_get(entity_id)
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

    for entity_id in (UPDATE_ENTITY_ID, REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        assert hass.states.get(entity_id) is None

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
    assert hass.states.get(UPDATE_ENTITY_ID) is not None

    dr.async_get(hass).async_remove_device(target_device.id)
    # Force re-resolution, mirroring a periodic bridge/devices republish.
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps([{"ieee_address": IEEE_ADDRESS, "friendly_name": FRIENDLY_NAME}]),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    for entity_id in (UPDATE_ENTITY_ID, REMOVE_ENTITY_ID, REINTERVIEW_ENTITY_ID):
        assert hass.states.get(entity_id) is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_remove_button_publishes_soft_remove(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": REMOVE_ENTITY_ID}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/remove", data={"id": IEEE_ADDRESS})
    assert sent == {
        "id": IEEE_ADDRESS,
        "force": False,
        "block": False,
        "transaction": sent["transaction"],
    }


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_reinterview_button_publishes_request(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    hass.async_create_task(hass.services.async_call("button", "press", {"entity_id": REINTERVIEW_ENTITY_ID}))
    sent = await async_respond_ok(
        hass, mqtt_mock, "zigbee2mqtt", "device/interview", data={"id": IEEE_ADDRESS}
    )
    assert sent["id"] == IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_ota_entity_reflects_progress(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    async_fire_mqtt_message(
        hass,
        f"zigbee2mqtt/{FRIENDLY_NAME}",
        json.dumps({"update": {"state": "updating", "progress": 42}}),
    )
    await hass.async_block_till_done()

    state = hass.states.get(UPDATE_ENTITY_ID)
    assert state.attributes["in_progress"] is True
    assert state.attributes["update_percentage"] == 42


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_ota_install_publishes_update_request(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    # HA's update component refuses install() unless latest_version differs
    # from installed_version - simulate Z2M reporting one available first
    # (and deliberately not "updating", which it would also refuse).
    async_fire_mqtt_message(
        hass, f"zigbee2mqtt/{FRIENDLY_NAME}", json.dumps({"update": {"state": "available"}})
    )
    await hass.async_block_till_done()

    hass.async_create_task(
        hass.services.async_call("update", "install", {"entity_id": UPDATE_ENTITY_ID}, blocking=False)
    )
    sent = await async_respond_ok(
        hass, mqtt_mock, "zigbee2mqtt", "device/ota_update/update", data={"id": IEEE_ADDRESS}
    )
    assert sent["id"] == IEEE_ADDRESS
