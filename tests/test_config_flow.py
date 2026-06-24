"""Tests for the Zigbee2MQTT Manager config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.zigbee2mqtt_manager.const import (
    CONF_BASE_TOPIC,
    CONF_NAME,
    CONF_NETWORKMAP_INTERVAL_HOURS,
    CONF_OFFLINE_THRESHOLD_MINUTES,
    CONF_OTA_CHECK_INTERVAL_DAYS,
    DEFAULT_NETWORKMAP_INTERVAL_HOURS,
    DEFAULT_OFFLINE_THRESHOLD_MINUTES,
    DEFAULT_OTA_CHECK_INTERVAL_DAYS,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Office Z2M", CONF_BASE_TOPIC: "zigbee2mqtt"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Office Z2M"
    assert result["data"] == {CONF_NAME: "Office Z2M", CONF_BASE_TOPIC: "zigbee2mqtt"}


async def test_user_flow_shows_options_fields_and_applies_their_defaults(hass: HomeAssistant) -> None:
    """The options-flow tunables must be visible (and pre-filled) on initial setup too.

    Only name/base_topic are explicitly submitted here - voluptuous fills
    every other field from the form's own defaults, which the step then
    splits off into the entry's options (see async_step_user).
    """
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert CONF_NETWORKMAP_INTERVAL_HOURS in result["data_schema"].schema
        assert CONF_OTA_CHECK_INTERVAL_DAYS in result["data_schema"].schema

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_NAME: "Office Z2M", CONF_BASE_TOPIC: "zigbee2mqtt"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_NETWORKMAP_INTERVAL_HOURS] == DEFAULT_NETWORKMAP_INTERVAL_HOURS
    assert result["options"][CONF_OTA_CHECK_INTERVAL_DAYS] == DEFAULT_OTA_CHECK_INTERVAL_DAYS
    assert result["result"].options == result["options"]


async def test_user_flow_stores_overridden_options(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Office Z2M",
                CONF_BASE_TOPIC: "zigbee2mqtt",
                CONF_NETWORKMAP_INTERVAL_HOURS: 6,
                CONF_OTA_CHECK_INTERVAL_DAYS: 7,
            },
        )

    assert result["options"][CONF_NETWORKMAP_INTERVAL_HOURS] == 6
    assert result["options"][CONF_OTA_CHECK_INTERVAL_DAYS] == 7
    # An untouched field still carries its own default through.
    assert result["options"][CONF_OFFLINE_THRESHOLD_MINUTES] == DEFAULT_OFFLINE_THRESHOLD_MINUTES


async def test_user_flow_defaults_name_to_base_topic(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BASE_TOPIC: "zigbee2mqtt_2"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "zigbee2mqtt_2"


async def test_user_flow_strips_slashes_from_base_topic(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BASE_TOPIC: "/zigbee2mqtt/"}
        )

    assert result["data"][CONF_BASE_TOPIC] == "zigbee2mqtt"


async def test_user_flow_aborts_when_mqtt_not_ready(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "mqtt_not_configured"


async def test_user_flow_rejects_duplicate_base_topic(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.zigbee2mqtt_manager.config_flow.mqtt.async_wait_for_mqtt_client",
        return_value=True,
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(first["flow_id"], {CONF_BASE_TOPIC: "zigbee2mqtt"})

        second = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            second["flow_id"], {CONF_BASE_TOPIC: "zigbee2mqtt"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
