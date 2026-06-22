"""Tests for Z2MHub's outgoing bridge/request commands.

Unlike test_hub.py (which feeds messages directly into the hub's handlers),
these tests need a real subscription in place to receive simulated responses,
so they go through mqtt_mock + a fully set-up hub. HA's MQTT client batches
new subscriptions behind a real INITIAL_SUBSCRIBE_COOLDOWN (0.5s) before they
become live for message routing - async_fire_mqtt_message bypasses the broker
but still goes through that same local routing table, so the hub fixture
below waits past the cooldown before yielding.

Important: once a request task is created, do NOT await
hass.async_block_till_done() before firing the simulated response -
hass.async_block_till_done() waits for *every* hass-tracked task to fully
finish, and the request task won't finish until either the response arrives
or its real (multi-second) timeout elapses. A short asyncio.sleep is used
instead to let the task progress only as far as its publish call.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.zigbee2mqtt_manager.hub import (
    Z2MHub,
    Z2MRequestError,
    Z2MRequestTimeoutError,
)

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


@pytest.fixture
async def hub(hass: HomeAssistant, mqtt_mock) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    await instance.async_setup()
    await asyncio.sleep(0.6)  # let the subscribe debouncer's cooldown elapse
    yield instance
    await instance.async_unload()


def _sent_payload(mqtt_mock, topic: str) -> dict:
    """Return the JSON payload of the most recent publish to topic."""
    for call in reversed(mqtt_mock.async_publish.mock_calls):
        if call.args[0] == topic:
            return json.loads(call.args[1])
    raise AssertionError(f"No publish to {topic} found")


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_async_permit_join_publishes_and_resolves(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    task = hass.async_create_task(hub.async_permit_join(120))
    await asyncio.sleep(0.05)  # let the task reach its publish call, no further

    sent = _sent_payload(mqtt_mock, f"{BASE_TOPIC}/bridge/request/permit_join")
    assert sent["time"] == 120
    transaction = sent["transaction"]

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/permit_join",
        json.dumps({"data": {"time": 120}, "status": "ok", "transaction": transaction}),
    )
    await hass.async_block_till_done()

    await task  # must not raise


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_async_restart_publishes_empty_payload(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    task = hass.async_create_task(hub.async_restart())
    await asyncio.sleep(0.05)  # let the task reach its publish call, no further

    sent = _sent_payload(mqtt_mock, f"{BASE_TOPIC}/bridge/request/restart")
    assert "transaction" in sent

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/restart",
        json.dumps({"data": {}, "status": "ok", "transaction": sent["transaction"]}),
    )
    await hass.async_block_till_done()
    await task


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_async_set_log_level_publishes_nested_options(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    task = hass.async_create_task(hub.async_set_log_level("debug"))
    await asyncio.sleep(0.05)  # let the task reach its publish call, no further

    sent = _sent_payload(mqtt_mock, f"{BASE_TOPIC}/bridge/request/options")
    assert sent["options"] == {"advanced": {"log_level": "debug"}}

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/options",
        json.dumps(
            {
                "data": {"restart_required": False},
                "status": "ok",
                "transaction": sent["transaction"],
            }
        ),
    )
    await hass.async_block_till_done()
    await task


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_request_raises_on_error_status(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    task = hass.async_create_task(hub.async_restart())
    await asyncio.sleep(0.05)  # let the task reach its publish call, no further

    sent = _sent_payload(mqtt_mock, f"{BASE_TOPIC}/bridge/request/restart")
    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/restart",
        json.dumps({"data": {}, "status": "error", "error": "boom", "transaction": sent["transaction"]}),
    )
    await hass.async_block_till_done()

    with pytest.raises(Z2MRequestError):
        await task


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_request_raises_on_timeout(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    with pytest.raises(Z2MRequestTimeoutError):
        await hub._async_request("restart", {}, timeout=0.01)

    # The pending entry must be cleaned up even after a timeout.
    assert hub._pending == {}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_request_with_nested_command_name_resolves(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    """Regression test: bridge/response/# must match multi-segment commands.

    A single-level "+" subscription would silently miss responses to
    commands like "device/remove" - this is exercised here against the real
    subscription (not by calling the handler directly) specifically to catch
    that class of bug.
    """
    task = hass.async_create_task(hub._async_request("device/remove", {"id": "my_bulb"}))
    await asyncio.sleep(0.05)

    sent = _sent_payload(mqtt_mock, f"{BASE_TOPIC}/bridge/request/device/remove")
    assert sent["id"] == "my_bulb"

    async_fire_mqtt_message(
        hass,
        f"{BASE_TOPIC}/bridge/response/device/remove",
        json.dumps({"data": {"id": "my_bulb"}, "status": "ok", "transaction": sent["transaction"]}),
    )
    await hass.async_block_till_done()

    result = await task
    assert result == {"id": "my_bulb"}
