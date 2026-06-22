"""Tests for Z2MHub.compute_offline_devices()'s dual auto-switching detection."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.zigbee2mqtt_manager.hub import Z2MHub
from custom_components.zigbee2mqtt_manager.models import DeviceAvailability, Z2MDevice

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


def _msg(topic: str, payload: str) -> ReceiveMessage:
    return ReceiveMessage(
        topic=topic, payload=payload, qos=0, retain=True, subscribed_topic=topic, timestamp=0.0
    )


@pytest.fixture
def hub(hass: HomeAssistant) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance", offline_threshold_minutes=15)
    instance.devices = {
        "0xAAA": Z2MDevice(ieee_address="0xAAA", friendly_name="has_availability"),
        "0xBBB": Z2MDevice(ieee_address="0xBBB", friendly_name="last_seen_only"),
        "0xCCC": Z2MDevice(ieee_address="0xCCC", friendly_name="no_signal_at_all"),
    }
    return instance


def test_availability_device_offline(hub: Z2MHub) -> None:
    hub._device_availability["0xAAA"] = DeviceAvailability(state="offline", since=dt_util.utcnow())

    offline = hub.compute_offline_devices()

    assert len(offline) == 1
    assert offline[0].ieee_address == "0xAAA"
    assert offline[0].detection == "availability"


def test_availability_device_online_is_not_offline_even_if_last_seen_stale(hub: Z2MHub) -> None:
    """A device with /availability is trusted exclusively - last_seen must not override it."""
    hub._device_availability["0xAAA"] = DeviceAvailability(state="online", since=dt_util.utcnow())
    hub._device_last_seen["0xAAA"] = dt_util.utcnow() - timedelta(days=30)

    offline = hub.compute_offline_devices()

    assert offline == []


def test_last_seen_fallback_when_no_availability(hub: Z2MHub) -> None:
    hub._device_last_seen["0xBBB"] = dt_util.utcnow() - timedelta(minutes=20)

    offline = hub.compute_offline_devices()

    assert len(offline) == 1
    assert offline[0].ieee_address == "0xBBB"
    assert offline[0].detection == "last_seen"


def test_last_seen_within_threshold_is_not_offline(hub: Z2MHub) -> None:
    hub._device_last_seen["0xBBB"] = dt_util.utcnow() - timedelta(minutes=5)

    offline = hub.compute_offline_devices()

    assert offline == []


def test_device_with_neither_signal_is_omitted_not_guessed(hub: Z2MHub) -> None:
    # 0xCCC has neither availability nor last_seen data at all.
    offline = hub.compute_offline_devices()

    assert all(device.ieee_address != "0xCCC" for device in offline)


def test_since_preserved_across_repeated_identical_state(hub: Z2MHub) -> None:
    """Re-publishing the same retained state must not reset 'how long offline'.

    Calls the real handler twice (not a re-implementation of its logic) so
    this actually exercises hub.py's code, not just this test's assumptions
    about it.
    """
    topic = f"{BASE_TOPIC}/has_availability/availability"

    hub._handle_device_availability(_msg(topic, json.dumps({"state": "offline"})))
    first_since = hub._device_availability["0xAAA"].since

    hub._handle_device_availability(_msg(topic, json.dumps({"state": "offline"})))
    second_since = hub._device_availability["0xAAA"].since

    assert first_since == second_since


def test_since_resets_on_actual_transition(hub: Z2MHub) -> None:
    """A real state transition must compute a fresh "since", not reuse the old one.

    Pre-seeds a deliberately-old "since" rather than comparing two live
    utcnow() calls back-to-back, which can land in the same microsecond and
    make the assertion flaky for reasons unrelated to the behavior under test.
    """
    stale_since = dt_util.utcnow() - timedelta(hours=5)
    hub._device_availability["0xAAA"] = DeviceAvailability(state="online", since=stale_since)

    topic = f"{BASE_TOPIC}/has_availability/availability"
    hub._handle_device_availability(_msg(topic, json.dumps({"state": "offline"})))

    assert hub._device_availability["0xAAA"].since != stale_since
