"""Config flow for Zigbee2MQTT Manager."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BASE_TOPIC,
    CONF_BATTERY_LOW_THRESHOLD_PERCENT,
    CONF_LOW_LQI_THRESHOLD,
    CONF_NAME,
    CONF_NETWORKMAP_INTERVAL_MINUTES,
    CONF_NETWORKMAP_ROUTES,
    CONF_NETWORKMAP_TYPE,
    CONF_OFFLINE_THRESHOLD_MINUTES,
    CONF_OTA_CHECK_INTERVAL_MINUTES,
    CONF_PERMIT_JOIN_DURATION,
    CONFIG_FLOW_MQTT_WAIT_TIMEOUT,
    DEFAULT_BASE_TOPIC,
    DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT,
    DEFAULT_LOW_LQI_THRESHOLD,
    DEFAULT_NETWORKMAP_INTERVAL_MINUTES,
    DEFAULT_NETWORKMAP_ROUTES,
    DEFAULT_NETWORKMAP_TYPE,
    DEFAULT_OFFLINE_THRESHOLD_MINUTES,
    DEFAULT_OTA_CHECK_INTERVAL_MINUTES,
    DEFAULT_PERMIT_JOIN_DURATION,
    DOMAIN,
    NETWORKMAP_TYPES,
)


class Z2MManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for one Zigbee2MQTT instance."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> Z2MManagerOptionsFlow:
        return Z2MManagerOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect the instance name and base topic."""
        if not await self._async_mqtt_ready():
            return self.async_abort(reason="mqtt_not_configured")

        errors: dict[str, str] = {}

        if user_input is not None:
            base_topic = user_input[CONF_BASE_TOPIC].strip("/")
            name = user_input.get(CONF_NAME) or base_topic

            if not base_topic:
                errors[CONF_BASE_TOPIC] = "base_topic_required"
            else:
                await self.async_set_unique_id(base_topic)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data={CONF_NAME: name, CONF_BASE_TOPIC: base_topic},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME): selector.TextSelector(),
                    vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): selector.TextSelector(),
                }
            ),
            errors=errors,
        )

    async def _async_mqtt_ready(self) -> bool:
        """Return whether HA's core mqtt integration has a connected client."""
        try:
            async with asyncio.timeout(CONFIG_FLOW_MQTT_WAIT_TIMEOUT):
                return await mqtt.async_wait_for_mqtt_client(self.hass)
        except TimeoutError:
            return False


class Z2MManagerOptionsFlow(OptionsFlow):
    """Tunable knobs that don't require re-adding the instance to change."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_OFFLINE_THRESHOLD_MINUTES,
                        default=options.get(
                            CONF_OFFLINE_THRESHOLD_MINUTES, DEFAULT_OFFLINE_THRESHOLD_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_NETWORKMAP_INTERVAL_MINUTES,
                        default=options.get(
                            CONF_NETWORKMAP_INTERVAL_MINUTES,
                            DEFAULT_NETWORKMAP_INTERVAL_MINUTES,
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_NETWORKMAP_TYPE,
                        default=options.get(CONF_NETWORKMAP_TYPE, DEFAULT_NETWORKMAP_TYPE),
                    ): selector.SelectSelector(selector.SelectSelectorConfig(options=NETWORKMAP_TYPES)),
                    vol.Optional(
                        CONF_NETWORKMAP_ROUTES,
                        default=options.get(CONF_NETWORKMAP_ROUTES, DEFAULT_NETWORKMAP_ROUTES),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_PERMIT_JOIN_DURATION,
                        default=options.get(CONF_PERMIT_JOIN_DURATION, DEFAULT_PERMIT_JOIN_DURATION),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=254, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_BATTERY_LOW_THRESHOLD_PERCENT,
                        default=options.get(
                            CONF_BATTERY_LOW_THRESHOLD_PERCENT, DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=100, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_LOW_LQI_THRESHOLD,
                        default=options.get(CONF_LOW_LQI_THRESHOLD, DEFAULT_LOW_LQI_THRESHOLD),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=255, mode=selector.NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_OTA_CHECK_INTERVAL_MINUTES,
                        default=options.get(
                            CONF_OTA_CHECK_INTERVAL_MINUTES, DEFAULT_OTA_CHECK_INTERVAL_MINUTES
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, mode=selector.NumberSelectorMode.BOX)
                    ),
                }
            ),
        )
