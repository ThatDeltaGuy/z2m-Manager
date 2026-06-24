"""Tests for Z2MHub's bulk OTA check (manual button + periodic timer)."""

from __future__ import annotations

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.zigbee2mqtt_manager.hub import Z2MHub, Z2MRequestTimeoutError
from custom_components.zigbee2mqtt_manager.models import Z2MDevice

from .helpers import PUBLISH_SETTLE_SECONDS

BASE_TOPIC = "zigbee2mqtt"
ENTRY_ID = "test_entry_id"


@pytest.fixture
def hub(hass: HomeAssistant) -> Z2MHub:
    instance = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    instance.devices = {
        "0xAAA": Z2MDevice(ieee_address="0xAAA", friendly_name="device_a"),
        "0xBBB": Z2MDevice(ieee_address="0xBBB", friendly_name="device_b"),
        "0xCOORD": Z2MDevice(ieee_address="0xCOORD", friendly_name="Coordinator", type="Coordinator"),
    }
    return instance


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_check_all_excludes_coordinator(hass: HomeAssistant, mqtt_mock, hub: Z2MHub) -> None:
    checked: list[str] = []

    async def _fake_ota_check(ieee_or_friendly: str) -> bool:
        checked.append(ieee_or_friendly)
        return False

    hub.async_ota_check = _fake_ota_check

    await hub.async_check_all_ota_updates()

    assert sorted(checked) == ["0xAAA", "0xBBB"]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_check_all_one_device_failure_does_not_abort_others(
    hass: HomeAssistant, mqtt_mock, hub: Z2MHub
) -> None:
    checked: list[str] = []

    async def _fake_ota_check(ieee_or_friendly: str) -> bool:
        if ieee_or_friendly == "0xAAA":
            raise Z2MRequestTimeoutError("device/ota_update/check", "tx")
        checked.append(ieee_or_friendly)
        return False

    hub.async_ota_check = _fake_ota_check

    await hub.async_check_all_ota_updates()  # must not raise

    assert checked == ["0xBBB"]


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_check_all_runs_concurrently_against_real_mqtt(hass: HomeAssistant, mqtt_mock) -> None:
    """End-to-end: both real bridge/request/device/ota_update/check publishes
    happen without waiting for one to finish before the other starts.
    """
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")
    hub.devices = {
        "0xAAA": Z2MDevice(ieee_address="0xAAA", friendly_name="device_a"),
        "0xBBB": Z2MDevice(ieee_address="0xBBB", friendly_name="device_b"),
    }
    await hub.async_setup()

    task = hass.async_create_task(hub.async_check_all_ota_updates())
    # Deliberately a short sleep, not hass.async_block_till_done(): that
    # waits for hass-tracked tasks to fully *complete*, and this task can't
    # complete until we respond below - it would block for the full
    # per-device request timeout instead of just letting the publish happen.
    await asyncio.sleep(PUBLISH_SETTLE_SECONDS)

    topic = f"{BASE_TOPIC}/bridge/request/device/ota_update/check"
    # Both requests must already be in flight - if they ran sequentially,
    # only one publish would exist at this point.
    sent_ids = {call.args[1] for call in mqtt_mock.async_publish.mock_calls if call.args[0] == topic}
    assert len(sent_ids) == 2

    for call in list(mqtt_mock.async_publish.mock_calls):
        if call.args[0] != topic:
            continue
        payload = json.loads(call.args[1])
        async_fire_mqtt_message(
            hass,
            f"{BASE_TOPIC}/bridge/response/device/ota_update/check",
            json.dumps(
                {
                    "data": {"update_available": False},
                    "status": "ok",
                    "transaction": payload["transaction"],
                }
            ),
        )
    await hass.async_block_till_done()
    await task

    await hub.async_unload()


def test_reschedule_ota_check_timer_zero_disables(hass: HomeAssistant) -> None:
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")

    hub._reschedule_ota_check_timer(60)
    assert hub._ota_check_timer_unsub is not None

    hub._reschedule_ota_check_timer(0)
    assert hub._ota_check_timer_unsub is None


def test_reschedule_ota_check_timer_cancels_previous(hass: HomeAssistant) -> None:
    hub = Z2MHub(hass, ENTRY_ID, BASE_TOPIC, "Test Instance")

    hub._reschedule_ota_check_timer(60)
    first_unsub = hub._ota_check_timer_unsub

    hub._reschedule_ota_check_timer(120)
    second_unsub = hub._ota_check_timer_unsub

    assert first_unsub is not second_unsub
    assert hub._ota_check_interval_days == 120

    hub._reschedule_ota_check_timer(0)  # cleanup so no real timer lingers


async def test_periodic_ota_check_calls_check_all(hass: HomeAssistant, hub: Z2MHub) -> None:
    called = []

    async def _fake_check_all() -> None:
        called.append(True)

    hub.async_check_all_ota_updates = _fake_check_all

    await hub._async_periodic_ota_check(None)

    assert called == [True]
