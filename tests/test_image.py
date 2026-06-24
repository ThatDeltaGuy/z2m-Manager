"""Tests for the per-device image entity.

Only created once Zigbee2MQTT has matched the device to a known definition
(bridge/devices[].definition.model) - that's the field Zigbee2MQTT's image
CDN keys off, distinct from the device's own raw "model_id" Zigbee string.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.zigbee2mqtt_manager.const import LINK_RECONCILE_DEBOUNCE
from custom_components.zigbee2mqtt_manager.image import _device_image_url

from .conftest import FRIENDLY_NAME, IEEE_ADDRESS

IMAGE_ENTITY_ID = "image.living_room_light_image"
SETTLE_SECONDS = LINK_RECONCILE_DEBOUNCE + 0.3


def test_device_image_url_encodes_special_characters() -> None:
    assert _device_image_url("WXKG01LM") == "https://www.zigbee2mqtt.io/images/devices/WXKG01LM.png"
    # Defensive only - real Zigbee2MQTT catalog models look like the above,
    # but the value still comes from external MQTT data, so a model
    # containing characters that would otherwise break the URL must still
    # produce a well-formed one rather than silently corrupting it.
    assert _device_image_url("A/B C") == "https://www.zigbee2mqtt.io/images/devices/A%2FB%20C.png"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_no_image_entity_without_definition_model(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    """linked_setup's bridge/devices payload has no "definition" field at all."""
    assert hass.states.get(IMAGE_ENTITY_ID) is None


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_image_entity_created_with_correct_url_once_model_known(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, _target_device = linked_setup

    # Republish with a now-known definition - mirrors Zigbee2MQTT completing
    # identification of a device some time after it first joined.
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {
                    "ieee_address": IEEE_ADDRESS,
                    "friendly_name": FRIENDLY_NAME,
                    "definition": {"model": "LED1545G12", "vendor": "IKEA"},
                }
            ]
        ),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    state = hass.states.get(IMAGE_ENTITY_ID)
    assert state is not None
    assert state.attributes["entity_picture"].startswith("/api/image_proxy/" + IMAGE_ENTITY_ID)
    # ImageEntity's state is its image_last_updated timestamp - without
    # setting that explicitly it would just be "unknown" forever even
    # though the image itself is perfectly valid.
    assert state.state != "unknown"
    dt_util.parse_datetime(state.state)  # raises if not a real timestamp

    # device_id attachment happens at platform-setup time (see
    # entity.async_attach_to_linked_device), not in async_added_to_hass -
    # this guards against that regressing back to a hook that wouldn't fire
    # for an entity disabled by default.
    entry = er.async_get(hass).async_get(IMAGE_ENTITY_ID)
    assert entry.device_id == _target_device.id
    assert entry.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_image_entity_disappears_when_device_becomes_unlinkable(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, target_device = linked_setup

    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {
                    "ieee_address": IEEE_ADDRESS,
                    "friendly_name": FRIENDLY_NAME,
                    "definition": {"model": "LED1545G12", "vendor": "IKEA"},
                }
            ]
        ),
    )
    await asyncio.sleep(SETTLE_SECONDS)
    assert hass.states.get(IMAGE_ENTITY_ID) is not None

    dr.async_get(hass).async_remove_device(target_device.id)
    async_fire_mqtt_message(
        hass,
        "zigbee2mqtt/bridge/devices",
        json.dumps(
            [
                {
                    "ieee_address": IEEE_ADDRESS,
                    "friendly_name": FRIENDLY_NAME,
                    "definition": {"model": "LED1545G12", "vendor": "IKEA"},
                }
            ]
        ),
    )
    await asyncio.sleep(SETTLE_SECONDS)

    assert hass.states.get(IMAGE_ENTITY_ID) is None
