"""Tests for domain-wide service registration and dispatch.

linked_setup (see conftest.py) gives a config entry whose hub already has
IEEE_ADDRESS linked, so call.data[ATTR_DEVICE_ID] -> hub lookups resolve.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.zigbee2mqtt_manager.const import DOMAIN

from .conftest import IEEE_ADDRESS
from .helpers import async_respond_ok


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_rename_device_resolves_device_id_to_ieee(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    _entry, target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "rename_device",
            {"device_id": target_device.id, "to_name": "kitchen_light"},
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/rename")

    assert sent["from"] == IEEE_ADDRESS
    assert sent["to"] == "kitchen_light"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_remove_device_service_passes_force_and_block(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "remove_device",
            {"device_id": target_device.id, "force": True, "block": True},
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/remove")

    assert sent["id"] == IEEE_ADDRESS
    assert sent["force"] is True
    assert sent["block"] is True


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_reinterview_device_service(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    _entry, target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(DOMAIN, "reinterview_device", {"device_id": target_device.id})
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/interview")

    assert sent["id"] == IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_device_targeted_service_rejects_unknown_device_id(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "reinterview_device",
            {"device_id": "not-a-real-device-id"},
            blocking=True,
        )


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_permit_join_service_with_config_entry_only(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(DOMAIN, "permit_join", {"config_entry_id": entry.entry_id, "time": 120})
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "permit_join")

    assert sent == {"time": 120, "transaction": sent["transaction"]}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_permit_join_service_scoped_to_linked_device(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "permit_join",
            {"config_entry_id": entry.entry_id, "time": 60, "device_id": target_device.id},
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "permit_join")

    assert sent["device"] == IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_permit_join_service_rejects_device_from_other_instance(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "permit_join",
            {
                "config_entry_id": entry.entry_id,
                "time": 60,
                "device_id": "some-other-integrations-device",
            },
            blocking=True,
        )


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_restart_service(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    entry, _target_device = linked_setup

    hass.async_create_task(hass.services.async_call(DOMAIN, "restart", {"config_entry_id": entry.entry_id}))
    await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "restart")


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_restart_service_rejects_foreign_config_entry_id(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, _target_device = linked_setup
    mqtt_entries = hass.config_entries.async_entries("mqtt")

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "restart",
            {"config_entry_id": mqtt_entries[0].entry_id},
            blocking=True,
        )


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_set_options_service_passes_nested_options(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "set_options",
            {
                "config_entry_id": entry.entry_id,
                "options": {"advanced": {"log_level": "debug"}},
            },
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "options")

    assert sent["options"] == {"advanced": {"log_level": "debug"}}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_ota_check_service_returns_response_data(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    _entry, target_device = linked_setup

    call_task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "ota_check",
            {"device_id": target_device.id},
            blocking=True,
            return_response=True,
        )
    )
    sent = await async_respond_ok(
        hass, mqtt_mock, "zigbee2mqtt", "device/ota_update/check", data={"update_available": True}
    )
    response = await call_task

    assert sent["id"] == IEEE_ADDRESS
    assert response == {"update_available": True}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_ota_update_service(hass: HomeAssistant, mqtt_mock, linked_setup) -> None:
    _entry, target_device = linked_setup

    hass.async_create_task(hass.services.async_call(DOMAIN, "ota_update", {"device_id": target_device.id}))
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "device/ota_update/update")

    assert sent["id"] == IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_refresh_networkmap_service_with_overrides(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "refresh_networkmap",
            {"config_entry_id": entry.entry_id, "type": "graphviz", "routes": True},
        )
    )
    sent = await async_respond_ok(
        hass,
        mqtt_mock,
        "zigbee2mqtt",
        "networkmap",
        data={"type": "graphviz", "value": "digraph G {}"},
    )

    assert sent["type"] == "graphviz"
    assert sent["routes"] is True


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_refresh_networkmap_service_defaults_to_configured_options(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    hass.async_create_task(
        hass.services.async_call(DOMAIN, "refresh_networkmap", {"config_entry_id": entry.entry_id})
    )
    sent = await async_respond_ok(
        hass, mqtt_mock, "zigbee2mqtt", "networkmap", data={"type": "raw", "value": {}}
    )

    assert sent["type"] == "raw"
    assert sent["routes"] is False


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_raw_command_service_round_trips_arbitrary_command(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, _target_device = linked_setup

    call_task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "raw_command",
            {
                "config_entry_id": entry.entry_id,
                "command": "touchlink/scan",
                "payload": {},
            },
            blocking=True,
            return_response=True,
        )
    )
    sent = await async_respond_ok(hass, mqtt_mock, "zigbee2mqtt", "touchlink/scan", data={"found": []})
    response = await call_task

    assert sent == {"transaction": sent["transaction"]}
    assert response == {"data": {"found": []}}


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_raw_command_service_rejects_foreign_config_entry_id(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    _entry, _target_device = linked_setup
    mqtt_entries = hass.config_entries.async_entries("mqtt")

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "raw_command",
            {"config_entry_id": mqtt_entries[0].entry_id, "command": "touchlink/scan"},
            blocking=True,
        )
