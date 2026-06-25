"""Tests for Z2MHub's battery/link-quality/OTA-available aggregate computation
and the _handle_device_state fix that lets battery/linkquality/update update
independently of one another.
"""

from __future__ import annotations

import json

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.zigbee2mqtt_manager.const import signal_device_metrics_changed
from custom_components.zigbee2mqtt_manager.hub import Z2MHub
from custom_components.zigbee2mqtt_manager.models import DeviceOtaState, Z2MDevice

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


def _msg(topic: str, payload: str) -> ReceiveMessage:
    return ReceiveMessage(
        topic=topic, payload=payload, qos=0, retain=True, subscribed_topic=topic, timestamp=0.0
    )


@pytest.fixture
def hub(hass: HomeAssistant) -> Z2MHub:
    instance = Z2MHub(
        hass,
        ENTRY_ID,
        BASE_TOPIC,
        "Test Instance",
        battery_low_threshold_percent=15,
        low_lqi_threshold=50,
    )
    instance.devices = {
        "0xAAA": Z2MDevice(ieee_address="0xAAA", friendly_name="sensor_a"),
        "0xBBB": Z2MDevice(ieee_address="0xBBB", friendly_name="sensor_b"),
        "0xCOORD": Z2MDevice(ieee_address="0xCOORD", friendly_name="Coordinator", type="Coordinator"),
    }
    return instance


# --- Battery -----------------------------------------------------------------


def test_battery_at_or_below_threshold_is_low(hub: Z2MHub) -> None:
    hub._device_battery["0xAAA"] = 15
    hub._device_battery["0xBBB"] = 16

    low = hub.compute_battery_low_devices()

    assert [d.ieee_address for d in low] == ["0xAAA"]
    assert low[0].battery == 15


def test_battery_excludes_coordinator(hub: Z2MHub) -> None:
    hub._device_battery["0xCOORD"] = 1  # even if Z2M somehow reported one

    assert hub.compute_battery_low_devices() == []


def test_battery_unknown_device_is_omitted(hub: Z2MHub) -> None:
    # 0xBBB never reported a battery field at all.
    assert hub.compute_battery_low_devices() == []


# --- Link quality --------------------------------------------------------------


def test_lqi_at_or_below_threshold_is_low(hub: Z2MHub) -> None:
    hub._device_linkquality["0xAAA"] = 50
    hub._device_linkquality["0xBBB"] = 51

    low = hub.compute_low_lqi_devices()

    assert [d.ieee_address for d in low] == ["0xAAA"]
    assert low[0].linkquality == 50


def test_lqi_excludes_coordinator(hub: Z2MHub) -> None:
    hub._device_linkquality["0xCOORD"] = 1

    assert hub.compute_low_lqi_devices() == []


# --- OTA available --------------------------------------------------------------


def test_ota_available_device_is_listed(hub: Z2MHub) -> None:
    hub.device_ota["0xAAA"] = DeviceOtaState(state="available")
    hub.device_ota["0xBBB"] = DeviceOtaState(state="idle")

    available = hub.compute_ota_available_devices()

    assert [d.ieee_address for d in available] == ["0xAAA"]


def test_ota_available_does_not_exclude_coordinator(hub: Z2MHub) -> None:
    """Unlike battery/LQI, some adapters do support Zigbee2MQTT-managed OTA."""
    hub.device_ota["0xCOORD"] = DeviceOtaState(state="available")

    available = hub.compute_ota_available_devices()

    assert [d.ieee_address for d in available] == ["0xCOORD"]


# --- _handle_device_state: independent field processing -----------------------


async def test_battery_and_linkquality_update_without_an_update_key(hass: HomeAssistant, hub: Z2MHub) -> None:
    topic = f"{BASE_TOPIC}/sensor_a"
    hub._handle_device_state(_msg(topic, json.dumps({"battery": 12, "linkquality": 40})))
    await hass.async_block_till_done()

    assert hub._device_battery["0xAAA"] == 12
    assert hub._device_linkquality["0xAAA"] == 40


async def test_metrics_changed_signal_fires_for_battery_alone(hass: HomeAssistant, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(
        hass, signal_device_metrics_changed(ENTRY_ID), lambda _data: received.append(True)
    )

    topic = f"{BASE_TOPIC}/sensor_a"
    hub._handle_device_state(_msg(topic, json.dumps({"battery": 50})))
    await hass.async_block_till_done()

    assert len(received) == 1


async def test_update_payload_still_populates_device_ota(hass: HomeAssistant, hub: Z2MHub) -> None:
    topic = f"{BASE_TOPIC}/sensor_a"
    hub._handle_device_state(_msg(topic, json.dumps({"update": {"state": "available", "progress": None}})))
    await hass.async_block_till_done()

    assert hub.device_ota["0xAAA"].state == "available"
