"""Tests for Z2MHub's network map refresh and periodic-timer scheduling."""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.zigbee2mqtt_manager.const import signal_networkmap
from custom_components.zigbee2mqtt_manager.hub import Z2MHub, Z2MRequestTimeoutError

from .helpers import async_get_last_publish

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


@pytest.fixture
async def hub(hass: HomeAssistant, mqtt_mock) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    await instance.async_setup()
    await asyncio.sleep(0.6)  # let the MQTT subscribe debouncer's cooldown elapse
    yield instance
    await instance.async_unload()


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_refresh_networkmap_publishes_configured_options(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    hub.networkmap_type = "graphviz"
    hub.networkmap_routes = True

    task = hass.async_create_task(hub.async_refresh_networkmap())
    sent = await async_get_last_publish(mqtt_mock, f"{BASE_TOPIC}/bridge/request/networkmap")
    assert sent["type"] == "graphviz"
    assert sent["routes"] is True

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/networkmap",
        json.dumps(
            {
                "data": {"type": "graphviz", "value": "digraph G {}"},
                "status": "ok",
                "transaction": sent["transaction"],
            }
        ),
    )
    await hass.async_block_till_done()

    result = await task
    assert result.type == "graphviz"
    assert result.value == "digraph G {}"
    assert hub.last_networkmap is result


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_refresh_networkmap_dispatches_signal(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    received = []
    async_dispatcher_connect(hass, signal_networkmap(ENTRY_ID), lambda result: received.append(result))

    task = hass.async_create_task(hub.async_refresh_networkmap())
    sent = await async_get_last_publish(mqtt_mock, f"{BASE_TOPIC}/bridge/request/networkmap")
    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/networkmap",
        json.dumps(
            {
                "data": {"type": "raw", "value": {"nodes": [], "links": []}},
                "status": "ok",
                "transaction": sent["transaction"],
            }
        ),
    )
    await hass.async_block_till_done()
    await task

    assert len(received) == 1
    assert received[0].value == {"nodes": [], "links": []}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_periodic_refresh_swallows_failures(hass: HomeAssistant, mqtt_mock) -> None:
    """A crashed scheduled callback would be worse than one missed refresh."""
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")

    async def _always_times_out(*args, **kwargs):
        raise Z2MRequestTimeoutError("networkmap", "tx")

    hub.async_refresh_networkmap = _always_times_out

    # Must not raise.
    await hub._async_periodic_networkmap_refresh(None)


def test_reschedule_timer_zero_disables(hass: HomeAssistant) -> None:
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")

    hub._reschedule_networkmap_timer(5)
    assert hub._networkmap_timer_unsub is not None

    hub._reschedule_networkmap_timer(0)
    assert hub._networkmap_timer_unsub is None


def test_reschedule_timer_cancels_previous(hass: HomeAssistant) -> None:
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")

    hub._reschedule_networkmap_timer(5)
    first_unsub = hub._networkmap_timer_unsub

    hub._reschedule_networkmap_timer(10)
    second_unsub = hub._networkmap_timer_unsub

    assert first_unsub is not second_unsub
    assert hub._networkmap_interval_minutes == 10

    hub._reschedule_networkmap_timer(0)  # cleanup so no real timer lingers
