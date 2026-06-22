"""Shared helpers for tests that exercise bridge/request <-> bridge/response."""

from __future__ import annotations

import asyncio
import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

# How long to let a just-created task run before assuming it has reached its
# bridge/request publish call. Must stay well clear of hass.async_block_till_done(),
# which would otherwise block for the request's full multi-second timeout
# since the request task it's waiting on hasn't resolved yet.
PUBLISH_SETTLE_SECONDS = 0.05


async def async_get_last_publish(mqtt_mock, topic: str) -> dict:
    """Return the JSON payload of the most recent publish to topic."""
    await asyncio.sleep(PUBLISH_SETTLE_SECONDS)
    for call in reversed(mqtt_mock.async_publish.mock_calls):
        if call.args[0] == topic:
            return json.loads(call.args[1])
    raise AssertionError(f"No publish to {topic} found")


async def async_respond_ok(
    hass: HomeAssistant, mqtt_mock, base_topic: str, command: str, data: dict | None = None
) -> dict:
    """Find the most recent request for `command` and answer it with status ok.

    Returns the payload that was sent, in case the caller wants to assert on it.
    """
    sent = await async_get_last_publish(mqtt_mock, f"{base_topic}/bridge/request/{command}")
    async_fire_mqtt_message(
        hass,
        f"{base_topic}/bridge/response/{command}",
        json.dumps({"data": data or {}, "status": "ok", "transaction": sent["transaction"]}),
    )
    await hass.async_block_till_done()
    return sent
