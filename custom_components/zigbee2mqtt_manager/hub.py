"""Hub owning all MQTT communication with a single Zigbee2MQTT instance."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CMD_DEVICE_INTERVIEW,
    CMD_DEVICE_OTA_CHECK,
    CMD_DEVICE_OTA_UPDATE,
    CMD_DEVICE_REMOVE,
    CMD_DEVICE_RENAME,
    CMD_NETWORKMAP,
    CMD_OPTIONS,
    CMD_PERMIT_JOIN,
    CMD_RESTART,
    CONF_BATTERY_LOW_THRESHOLD_PERCENT,
    CONF_LOW_LQI_THRESHOLD,
    CONF_NETWORKMAP_INTERVAL_HOURS,
    CONF_NETWORKMAP_ROUTES,
    CONF_NETWORKMAP_TYPE,
    CONF_OFFLINE_THRESHOLD_MINUTES,
    CONF_OTA_CHECK_INTERVAL_DAYS,
    CONF_PERMIT_JOIN_DURATION,
    CONF_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT,
    CONF_REMOVE_BUTTON_ENABLED_BY_DEFAULT,
    COORDINATOR_DEVICE_TYPE,
    DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT,
    DEFAULT_LOW_LQI_THRESHOLD,
    DEFAULT_NETWORKMAP_INTERVAL_HOURS,
    DEFAULT_NETWORKMAP_ROUTES,
    DEFAULT_NETWORKMAP_TYPE,
    DEFAULT_OFFLINE_THRESHOLD_MINUTES,
    DEFAULT_OTA_CHECK_INTERVAL_DAYS,
    DEFAULT_PERMIT_JOIN_DURATION,
    DEFAULT_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT,
    DEFAULT_REMOVE_BUTTON_ENABLED_BY_DEFAULT,
    LINK_RECONCILE_DEBOUNCE,
    REQUEST_TIMEOUT_DEFAULT,
    REQUEST_TIMEOUT_NETWORKMAP,
    REQUEST_TIMEOUT_OTA_CHECK,
    REQUEST_TIMEOUT_OTA_UPDATE,
    signal_bridge_groups,
    signal_bridge_info,
    signal_bridge_state,
    signal_device_availability,
    signal_device_linkable,
    signal_device_metrics_changed,
    signal_device_unlinkable,
    signal_devices,
    signal_networkmap,
    signal_offline_candidates_changed,
)
from .device_link import (
    LinkResult,
    async_get_mqtt_config_entry_id,
    find_ha_device_for_z2m_device,
)
from .models import (
    BatteryLowDevice,
    BridgeInfo,
    DeviceAvailability,
    DeviceLinkedPayload,
    DeviceOtaState,
    LowLqiDevice,
    NetworkMapResult,
    OfflineDevice,
    OtaAvailableDevice,
    Z2MDevice,
    Z2MGroup,
)

_LOGGER = logging.getLogger(__name__)


class Z2MMqttUnavailableError(Exception):
    """Raised when the MQTT integration's client never becomes available."""


class Z2MRequestError(Exception):
    """Raised when a bridge/request command returns status != "ok"."""

    def __init__(self, command: str, error: str) -> None:
        super().__init__(f"Zigbee2MQTT request '{command}' failed: {error}")
        self.command = command
        self.error = error


class Z2MRequestTimeoutError(Exception):
    """Raised when a bridge/request command receives no response in time."""

    def __init__(self, command: str, transaction: str) -> None:
        super().__init__(f"Zigbee2MQTT request '{command}' (transaction {transaction}) timed out")
        self.command = command
        self.transaction = transaction


class Z2MHub:
    """Owns MQTT subscriptions, parsed bridge state, and outgoing requests.

    One instance per config entry (per Zigbee2MQTT instance). Entities never
    talk to MQTT directly - they read parsed state off this hub and listen for
    dispatcher signals it sends, or call its async_* command methods.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        base_topic: str,
        name: str,
        *,
        permit_join_duration: int = DEFAULT_PERMIT_JOIN_DURATION,
        offline_threshold_minutes: int = DEFAULT_OFFLINE_THRESHOLD_MINUTES,
        networkmap_interval_hours: int = 0,
        networkmap_type: str = DEFAULT_NETWORKMAP_TYPE,
        networkmap_routes: bool = DEFAULT_NETWORKMAP_ROUTES,
        battery_low_threshold_percent: int = DEFAULT_BATTERY_LOW_THRESHOLD_PERCENT,
        low_lqi_threshold: int = DEFAULT_LOW_LQI_THRESHOLD,
        ota_check_interval_days: int = 0,
        remove_button_enabled_by_default: bool = DEFAULT_REMOVE_BUTTON_ENABLED_BY_DEFAULT,
        reinterview_button_enabled_by_default: bool = DEFAULT_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.base_topic = base_topic
        self.name = name
        self.permit_join_duration = permit_join_duration
        self.offline_threshold_minutes = offline_threshold_minutes
        self.networkmap_type = networkmap_type
        self.networkmap_routes = networkmap_routes
        self.battery_low_threshold_percent = battery_low_threshold_percent
        self.low_lqi_threshold = low_lqi_threshold
        # Only consulted at entity-creation time (HA reads
        # entity_registry_enabled_default once, when an entity is first
        # registered) - changing these via the options flow only affects
        # devices that link/relink afterwards, not entities that already
        # exist. That's standard HA behavior for this setting, not a bug.
        self.remove_button_enabled_by_default = remove_button_enabled_by_default
        self.reinterview_button_enabled_by_default = reinterview_button_enabled_by_default

        self.bridge_info: BridgeInfo | None = None
        self.bridge_online: bool = False
        self.devices: dict[str, Z2MDevice] = {}
        self.groups: dict[int, Z2MGroup] = {}
        self.device_ota: dict[str, DeviceOtaState] = {}
        self.last_networkmap: NetworkMapResult | None = None

        self._device_availability: dict[str, DeviceAvailability] = {}
        self._device_last_seen: dict[str, datetime] = {}
        self._device_battery: dict[str, int] = {}
        self._device_linkquality: dict[str, int] = {}
        self._networkmap_interval_hours = networkmap_interval_hours
        self._networkmap_timer_unsub: Any = None
        self._ota_check_interval_days = ota_check_interval_days
        self._ota_check_timer_unsub: Any = None

        # device_id -> ieee_address, maintained for free during link
        # reconciliation; lets services resolve a targeted HA device back to
        # an ieee_address without parsing it out of a unique_id string.
        self.device_id_to_ieee: dict[str, str] = {}

        self._pending: dict[tuple[str, str], asyncio.Future[dict[str, Any]]] = {}
        self._unsubscribes: list[Any] = []
        self._mqtt_config_entry_id: str | None = None
        self._link_cache: dict[str, LinkResult] = {}
        self._link_reconcile_unsub: Any = None

    async def async_setup(self) -> None:
        """Wait for the MQTT client and subscribe to all bridge-level topics."""
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise Z2MMqttUnavailableError("The MQTT integration is not set up or its client never connected")

        self._mqtt_config_entry_id = async_get_mqtt_config_entry_id(self.hass)

        self._unsubscribes.append(
            await mqtt.async_subscribe(self.hass, f"{self.base_topic}/bridge/info", self._handle_bridge_info)
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base_topic}/bridge/state", self._handle_bridge_state
            )
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base_topic}/bridge/devices", self._handle_bridge_devices
            )
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.base_topic}/bridge/groups", self._handle_bridge_groups
            )
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(
                self.hass,
                # Multi-level wildcard: several commands are nested (e.g.
                # "device/remove", "device/ota_update/check") - a single-level
                # "+" would silently miss every response to those.
                f"{self.base_topic}/bridge/response/#",
                self._handle_bridge_response,
            )
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(self.hass, f"{self.base_topic}/+", self._handle_device_state)
        )
        self._unsubscribes.append(
            await mqtt.async_subscribe(
                self.hass,
                f"{self.base_topic}/+/availability",
                self._handle_device_availability,
            )
        )

        self._reschedule_networkmap_timer(self._networkmap_interval_hours)
        self._reschedule_ota_check_timer(self._ota_check_interval_days)

    async def async_unload(self) -> None:
        """Unsubscribe from every topic and cancel any in-flight requests."""
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()

        if self._link_reconcile_unsub is not None:
            self._link_reconcile_unsub()
            self._link_reconcile_unsub = None

        if self._networkmap_timer_unsub is not None:
            self._networkmap_timer_unsub()
            self._networkmap_timer_unsub = None

        if self._ota_check_timer_unsub is not None:
            self._ota_check_timer_unsub()
            self._ota_check_timer_unsub = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    # --- Outgoing requests ---------------------------------------------------

    async def _async_request(
        self,
        command: str,
        payload: dict[str, Any],
        *,
        timeout: float = REQUEST_TIMEOUT_DEFAULT,
    ) -> dict[str, Any]:
        """Publish to bridge/request/<command> and await the matching response.

        Every bridge command funnels through here so transaction-correlation
        and timeout/error handling only needs to be correct in one place.
        """
        transaction = str(uuid.uuid4())
        future: asyncio.Future[dict[str, Any]] = self.hass.loop.create_future()
        self._pending[(command, transaction)] = future
        try:
            await mqtt.async_publish(
                self.hass,
                f"{self.base_topic}/bridge/request/{command}",
                json.dumps({**payload, "transaction": transaction}),
                qos=0,
                retain=False,
            )
            response = await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as err:
            _LOGGER.warning(
                "Zigbee2MQTT request '%s' timed out after %.0fs waiting for "
                "%s/bridge/response/%s - the bridge may be slow to respond, "
                "or this exact command may not be supported by this version "
                "of Zigbee2MQTT",
                command,
                timeout,
                self.base_topic,
                command,
            )
            raise Z2MRequestTimeoutError(command, transaction) from err
        finally:
            self._pending.pop((command, transaction), None)

        if response.get("status") != "ok":
            error = response.get("error", "unknown error")
            _LOGGER.warning("Zigbee2MQTT request '%s' failed: %s", command, error)
            raise Z2MRequestError(command, error)
        return response.get("data", {})

    async def async_permit_join(self, time_s: int, device: str | None = None) -> None:
        """Allow (time_s > 0) or disallow (time_s == 0) new devices to join.

        device, if given (an ieee_address or friendly_name), scopes the
        permission to that router rather than the whole network - mainly
        useful for automations; the bridge-level switch always targets the
        whole network.
        """
        payload: dict[str, Any] = {"time": time_s}
        if device is not None:
            payload["device"] = device
        await self._async_request(CMD_PERMIT_JOIN, payload)

    async def async_restart(self) -> None:
        """Restart the Zigbee2MQTT instance."""
        await self._async_request(CMD_RESTART, {})

    async def async_set_log_level(self, level: str) -> None:
        """Change Zigbee2MQTT's runtime log level."""
        await self._async_request(CMD_OPTIONS, {"options": {"advanced": {"log_level": level}}})

    async def async_rename_device(self, from_name: str, to_name: str) -> None:
        """Rename a device.

        Service-only (see button.py) - renaming needs a new-name argument,
        which a parameterless ButtonEntity can't take, and a persistent text
        helper would be the wrong fit for a one-shot command.
        """
        await self._async_request(CMD_DEVICE_RENAME, {"from": from_name, "to": to_name})

    async def async_remove_device(
        self, ieee_or_friendly: str, *, force: bool = False, block: bool = False
    ) -> None:
        """Remove a device from the Zigbee network.

        block prevents it from immediately rejoining - exposed only via the
        remove_device service (see services.py), not the dashboard button,
        for the same "avoid a destructive misclick" reasoning as force.
        """
        await self._async_request(CMD_DEVICE_REMOVE, {"id": ieee_or_friendly, "force": force, "block": block})

    async def async_reinterview_device(self, ieee_or_friendly: str) -> None:
        """Force a re-interview of a device."""
        await self._async_request(CMD_DEVICE_INTERVIEW, {"id": ieee_or_friendly})

    async def async_ota_check(self, ieee_or_friendly: str) -> bool:
        """Check whether a firmware update is available; returns update_available."""
        data = await self._async_request(
            CMD_DEVICE_OTA_CHECK, {"id": ieee_or_friendly}, timeout=REQUEST_TIMEOUT_OTA_CHECK
        )
        return bool(data.get("update_available", False))

    async def async_ota_update(self, ieee_or_friendly: str) -> None:
        """Install a firmware update.

        Long-running: Zigbee2MQTT reports progress via the device's own state
        topic's "update" object (see _handle_device_state), not via this
        response - the response just acknowledges the update started/finished.
        """
        await self._async_request(
            CMD_DEVICE_OTA_UPDATE, {"id": ieee_or_friendly}, timeout=REQUEST_TIMEOUT_OTA_UPDATE
        )

    async def async_refresh_networkmap(
        self, *, type: str | None = None, routes: bool | None = None
    ) -> NetworkMapResult:
        """Request a fresh network map and store/dispatch the result.

        type/routes default to the options-flow-configured values; the
        refresh_networkmap service (see services.py) can override either for
        a one-off request without changing the stored configuration.
        """
        data = await self._async_request(
            CMD_NETWORKMAP,
            {
                "type": type if type is not None else self.networkmap_type,
                "routes": routes if routes is not None else self.networkmap_routes,
            },
            timeout=REQUEST_TIMEOUT_NETWORKMAP,
        )
        return self._apply_networkmap_data(data)

    def _apply_networkmap_data(self, data: dict[str, Any]) -> NetworkMapResult:
        result = NetworkMapResult(
            refreshed_at=dt_util.utcnow(),
            type=data.get("type", self.networkmap_type),
            value=data.get("value"),
        )
        self.last_networkmap = result
        async_dispatcher_send(self.hass, signal_networkmap(self.entry_id), result)
        return result

    async def async_raw_passthrough(
        self, command: str, payload: dict[str, Any], *, timeout: float = REQUEST_TIMEOUT_DEFAULT
    ) -> dict[str, Any]:
        """Publish an arbitrary bridge/request/<command> and return its response data.

        The escape hatch backing the raw_command service (see services.py)
        for anything without a dedicated entity/method - touchlink, group
        management, etc. - without needing this hub to model every Zigbee2MQTT
        bridge command up front.
        """
        return await self._async_request(command, payload, timeout=timeout)

    async def async_check_all_ota_updates(self) -> None:
        """Check every known device (excluding the coordinator) for a firmware update.

        Runs concurrently rather than one-at-a-time - Zigbee2MQTT serializes
        the actual radio traffic on its end regardless, so there is no
        benefit to waiting out one device's full timeout before even
        starting the next. Each device's failure is logged and otherwise
        ignored so one unresponsive device can't abort the whole sweep -
        the resulting per-device OTA state still arrives independently via
        Zigbee2MQTT's own state republish (see _handle_device_state).
        """
        ieee_addresses = [
            ieee_address
            for ieee_address, device in self.devices.items()
            if device.type != COORDINATOR_DEVICE_TYPE
        ]

        async def _check_one(ieee_address: str) -> None:
            try:
                await self.async_ota_check(ieee_address)
            except (Z2MRequestError, Z2MRequestTimeoutError) as err:
                _LOGGER.warning("OTA check failed for %s: %s", ieee_address, err)

        await asyncio.gather(*(_check_one(ieee_address) for ieee_address in ieee_addresses))

    async def _async_periodic_networkmap_refresh(self, _now: datetime) -> None:
        """Timer-driven refresh - logs and swallows failures rather than raising.

        A crashed scheduled callback would be a worse failure mode than one
        missed periodic refresh (the manual refresh button is unaffected).
        """
        try:
            await self.async_refresh_networkmap()
        except (Z2MRequestError, Z2MRequestTimeoutError) as err:
            _LOGGER.warning("Periodic network map refresh failed: %s", err)

    def _reschedule_networkmap_timer(self, interval_hours: int) -> None:
        """(Re)start the periodic refresh timer; 0 disables it."""
        if self._networkmap_timer_unsub is not None:
            self._networkmap_timer_unsub()
            self._networkmap_timer_unsub = None

        self._networkmap_interval_hours = interval_hours
        if interval_hours > 0:
            self._networkmap_timer_unsub = async_track_time_interval(
                self.hass,
                self._async_periodic_networkmap_refresh,
                timedelta(hours=interval_hours),
            )

    async def _async_periodic_ota_check(self, _now: datetime) -> None:
        """Timer-driven OTA sweep.

        async_check_all_ota_updates already logs and swallows per-device
        failures, so there is nothing further to catch here.
        """
        await self.async_check_all_ota_updates()

    def _reschedule_ota_check_timer(self, interval_days: int) -> None:
        """(Re)start the periodic OTA-check timer; 0 disables it."""
        if self._ota_check_timer_unsub is not None:
            self._ota_check_timer_unsub()
            self._ota_check_timer_unsub = None

        self._ota_check_interval_days = interval_days
        if interval_days > 0:
            self._ota_check_timer_unsub = async_track_time_interval(
                self.hass,
                self._async_periodic_ota_check,
                timedelta(days=interval_days),
            )

    async def async_update_options(self, options: dict[str, Any]) -> None:
        """Apply new options-flow values without requiring a reload."""
        self.permit_join_duration = options.get(CONF_PERMIT_JOIN_DURATION, self.permit_join_duration)
        self.offline_threshold_minutes = options.get(
            CONF_OFFLINE_THRESHOLD_MINUTES, self.offline_threshold_minutes
        )
        self.networkmap_type = options.get(CONF_NETWORKMAP_TYPE, self.networkmap_type)
        self.networkmap_routes = options.get(CONF_NETWORKMAP_ROUTES, self.networkmap_routes)
        self.battery_low_threshold_percent = options.get(
            CONF_BATTERY_LOW_THRESHOLD_PERCENT, self.battery_low_threshold_percent
        )
        self.low_lqi_threshold = options.get(CONF_LOW_LQI_THRESHOLD, self.low_lqi_threshold)
        self.remove_button_enabled_by_default = options.get(
            CONF_REMOVE_BUTTON_ENABLED_BY_DEFAULT, self.remove_button_enabled_by_default
        )
        self.reinterview_button_enabled_by_default = options.get(
            CONF_REINTERVIEW_BUTTON_ENABLED_BY_DEFAULT, self.reinterview_button_enabled_by_default
        )
        self._reschedule_networkmap_timer(
            options.get(CONF_NETWORKMAP_INTERVAL_HOURS, DEFAULT_NETWORKMAP_INTERVAL_HOURS)
        )
        self._reschedule_ota_check_timer(
            options.get(CONF_OTA_CHECK_INTERVAL_DAYS, DEFAULT_OTA_CHECK_INTERVAL_DAYS)
        )

    def compute_offline_devices(self) -> list[OfflineDevice]:
        """Per-device auto-switching offline detection.

        A device that has ever published an /availability message is trusted
        exclusively via that signal; otherwise last_seen is compared against
        the configurable threshold. A device with neither signal is correctly
        omitted rather than guessed at.

        The coordinator is excluded: it doesn't send Zigbee messages to
        itself, so its last_seen (if Zigbee2MQTT reports one at all) rarely
        if ever updates and would otherwise be perpetually misreported as
        offline via the last_seen fallback - its actual connectivity is
        already covered by the bridge connectivity sensor (bridge/state).

        Each device's evaluation is wrapped individually: unexpected data
        from one device (e.g. an unparseable timestamp) must not take down
        the whole sensor for every other device too.
        """
        offline: list[OfflineDevice] = []
        now = dt_util.utcnow()
        threshold = timedelta(minutes=self.offline_threshold_minutes)

        for ieee_address, device in self.devices.items():
            if device.type == COORDINATOR_DEVICE_TYPE:
                continue
            try:
                availability = self._device_availability.get(ieee_address)
                if availability is not None:
                    if availability.state == "offline":
                        offline.append(
                            OfflineDevice(
                                ieee_address=ieee_address,
                                friendly_name=device.friendly_name,
                                detection="availability",
                                since=availability.since,
                            )
                        )
                    continue

                last_seen = self._device_last_seen.get(ieee_address)
                if last_seen is not None and (now - last_seen) > threshold:
                    offline.append(
                        OfflineDevice(
                            ieee_address=ieee_address,
                            friendly_name=device.friendly_name,
                            detection="last_seen",
                            since=last_seen,
                        )
                    )
            except Exception:
                _LOGGER.warning(
                    "Failed to evaluate offline status for %s", device.friendly_name, exc_info=True
                )

        return offline

    def compute_battery_low_devices(self) -> list[BatteryLowDevice]:
        """Devices (excluding the coordinator, which has no battery) at or
        below the configured battery threshold.
        """
        low_battery: list[BatteryLowDevice] = []
        for ieee_address, device in self.devices.items():
            if device.type == COORDINATOR_DEVICE_TYPE:
                continue
            battery = self._device_battery.get(ieee_address)
            if battery is None:
                continue
            try:
                if battery <= self.battery_low_threshold_percent:
                    low_battery.append(
                        BatteryLowDevice(
                            ieee_address=ieee_address,
                            friendly_name=device.friendly_name,
                            battery=battery,
                        )
                    )
            except Exception:
                _LOGGER.warning(
                    "Failed to evaluate battery level for %s", device.friendly_name, exc_info=True
                )
        return low_battery

    def compute_low_lqi_devices(self) -> list[LowLqiDevice]:
        """Devices (excluding the coordinator) at or below the configured
        link-quality threshold.
        """
        low_lqi: list[LowLqiDevice] = []
        for ieee_address, device in self.devices.items():
            if device.type == COORDINATOR_DEVICE_TYPE:
                continue
            linkquality = self._device_linkquality.get(ieee_address)
            if linkquality is None:
                continue
            try:
                if linkquality <= self.low_lqi_threshold:
                    low_lqi.append(
                        LowLqiDevice(
                            ieee_address=ieee_address,
                            friendly_name=device.friendly_name,
                            linkquality=linkquality,
                        )
                    )
            except Exception:
                _LOGGER.warning("Failed to evaluate link quality for %s", device.friendly_name, exc_info=True)
        return low_lqi

    def compute_ota_available_devices(self) -> list[OtaAvailableDevice]:
        """Devices with a firmware update currently available.

        The coordinator is not excluded here (unlike the other aggregate
        sensors): some Zigbee adapters do support Zigbee2MQTT-managed
        firmware updates, and there's no reason to hide that if Zigbee2MQTT
        reports it.
        """
        available: list[OtaAvailableDevice] = []
        for ieee_address, device in self.devices.items():
            ota_state = self.device_ota.get(ieee_address)
            if ota_state is None:
                continue
            try:
                if ota_state.state == "available":
                    available.append(
                        OtaAvailableDevice(ieee_address=ieee_address, friendly_name=device.friendly_name)
                    )
            except Exception:
                _LOGGER.warning("Failed to evaluate OTA state for %s", device.friendly_name, exc_info=True)
        return available

    # --- Device-link reconciliation ------------------------------------------

    @callback
    def _schedule_link_reconciliation(self) -> None:
        """Debounce reconciliation - bridge/devices can republish several
        times in quick succession during a pairing session, and re-scanning
        the device registry on every single one is wasteful and would also
        cause entity add/remove churn.
        """
        if self._link_reconcile_unsub is not None:
            self._link_reconcile_unsub()
        self._link_reconcile_unsub = async_call_later(
            self.hass, LINK_RECONCILE_DEBOUNCE, self._async_reconcile_links
        )

    async def _async_reconcile_links(self, _now: datetime | None = None) -> None:
        """Re-resolve every known device's link, signalling only on change.

        This is what makes "linkability changes dynamically over time" work:
        a device that becomes linkable while running fires
        signal_device_linkable immediately, not just at the next HA restart.
        """
        self._link_reconcile_unsub = None
        known_ieee_addresses = set(self.devices)

        # A device Zigbee2MQTT no longer reports (removed from the network)
        # must be unlinked too, not just left stale in the cache.
        for ieee_address in [a for a in self._link_cache if a not in known_ieee_addresses]:
            self._async_forget_link(ieee_address)

        for ieee_address, device in self.devices.items():
            new_result = find_ha_device_for_z2m_device(
                self.hass,
                ieee_address=ieee_address,
                friendly_name=device.friendly_name,
                mqtt_config_entry_id=self._mqtt_config_entry_id,
            )
            previous_result = self._link_cache.get(ieee_address)
            if previous_result is not None and previous_result.ha_device_id == new_result.ha_device_id:
                continue  # unchanged (including "still not_found") - nothing to signal

            if previous_result is not None and previous_result.ha_device_id is not None:
                self._async_forget_link(ieee_address)

            self._link_cache[ieee_address] = new_result
            if new_result.ha_device_id is not None:
                self.device_id_to_ieee[new_result.ha_device_id] = ieee_address
                async_dispatcher_send(
                    self.hass,
                    signal_device_linkable(self.entry_id),
                    DeviceLinkedPayload(ieee_address=ieee_address, ha_device_id=new_result.ha_device_id),
                )

    def _async_forget_link(self, ieee_address: str) -> None:
        """Drop a cached link and tell existing per-device entities to remove themselves."""
        previous = self._link_cache.pop(ieee_address, None)
        if previous is not None and previous.ha_device_id is not None:
            self.device_id_to_ieee.pop(previous.ha_device_id, None)
        async_dispatcher_send(self.hass, signal_device_unlinkable(self.entry_id), ieee_address)

    # --- Incoming message handlers ------------------------------------------

    @callback
    def _handle_bridge_info(self, msg: mqtt.ReceiveMessage) -> None:
        payload = _parse_json(msg.topic, msg.payload)
        if payload is None:
            return

        self.bridge_info = BridgeInfo(
            version=payload.get("version"),
            commit=payload.get("commit"),
            coordinator=payload.get("coordinator", {}),
            network=payload.get("network", {}),
            log_level=payload.get("log_level"),
            permit_join=bool(payload.get("permit_join", False)),
            permit_join_end=payload.get("permit_join_end"),
            raw=payload,
        )
        async_dispatcher_send(self.hass, signal_bridge_info(self.entry_id), self.bridge_info)

    @callback
    def _handle_bridge_state(self, msg: mqtt.ReceiveMessage) -> None:
        # Most current Zigbee2MQTT versions publish {"state": "online"|"offline"},
        # but older versions published the bare string - handle both.
        payload = _parse_json(msg.topic, msg.payload)
        state = payload.get("state") if payload is not None else msg.payload

        self.bridge_online = state == "online"
        async_dispatcher_send(self.hass, signal_bridge_state(self.entry_id), self.bridge_online)

    @callback
    def _handle_bridge_devices(self, msg: mqtt.ReceiveMessage) -> None:
        payload = _parse_json(msg.topic, msg.payload)
        if payload is None:
            return

        devices: dict[str, Z2MDevice] = {}
        for item in payload:
            ieee_address = item.get("ieee_address")
            if not ieee_address:
                continue
            # "definition" is explicitly null for devices Zigbee2MQTT hasn't
            # matched to a known definition (e.g. mid-interview) - .get()
            # would still raise on None.get(...), so guard with `or {}`.
            definition = item.get("definition") or {}
            devices[ieee_address] = Z2MDevice(
                ieee_address=ieee_address,
                friendly_name=item.get("friendly_name", ieee_address),
                type=item.get("type"),
                model_id=item.get("model_id"),
                definition_model=definition.get("model"),
                power_source=item.get("power_source"),
                software_build_id=item.get("software_build_id"),
                date_code=item.get("date_code"),
                supported=item.get("supported", True),
                disabled=item.get("disabled", False),
                interview_completed=item.get("interview_completed", True),
                raw=item,
            )
        self.devices = devices
        async_dispatcher_send(self.hass, signal_devices(self.entry_id), self.devices)
        async_dispatcher_send(self.hass, signal_offline_candidates_changed(self.entry_id), None)
        self._schedule_link_reconciliation()

    @callback
    def _handle_device_state(self, msg: mqtt.ReceiveMessage) -> None:
        friendly_name = msg.topic.removeprefix(f"{self.base_topic}/")
        if friendly_name == "bridge":
            # Defensive only: bridge/* topics are two levels deep
            # (e.g. "bridge/info") and a single-level "+" subscription
            # should never actually deliver a bare "bridge" topic, but this
            # guards against Zigbee2MQTT ever publishing one directly.
            return

        payload = _parse_json(msg.topic, msg.payload)
        if not isinstance(payload, dict):
            return

        ieee_address = next(
            (d.ieee_address for d in self.devices.values() if d.friendly_name == friendly_name),
            None,
        )
        if ieee_address is None:
            return  # device not (yet) known via bridge/devices - nothing to attach this to

        last_seen = _parse_last_seen(payload.get("last_seen"))
        if last_seen is not None:
            self._device_last_seen[ieee_address] = last_seen
            async_dispatcher_send(self.hass, signal_offline_candidates_changed(self.entry_id), None)

        # battery/linkquality/update are independent, optional fields - a
        # device without one shouldn't skip the others (this used to return
        # early on a missing "update" key, which silently dropped
        # battery/linkquality for every device that doesn't report OTA data).
        metrics_changed = False

        battery = payload.get("battery")
        if isinstance(battery, (int, float)):
            self._device_battery[ieee_address] = int(battery)
            metrics_changed = True

        linkquality = payload.get("linkquality")
        if isinstance(linkquality, (int, float)):
            self._device_linkquality[ieee_address] = int(linkquality)
            metrics_changed = True

        update_payload = payload.get("update")
        if isinstance(update_payload, dict):
            # Tracked for the bridge-level OTA-available aggregate sensor
            # only - there's no per-device update entity here, since
            # Zigbee2MQTT's own MQTT discovery already provides one.
            self.device_ota[ieee_address] = DeviceOtaState(
                state=update_payload.get("state"),
                progress=update_payload.get("progress"),
                remaining_time=update_payload.get("remaining_time"),
            )
            metrics_changed = True

        if metrics_changed:
            async_dispatcher_send(self.hass, signal_device_metrics_changed(self.entry_id), None)

    @callback
    def _handle_device_availability(self, msg: mqtt.ReceiveMessage) -> None:
        friendly_name = msg.topic.removeprefix(f"{self.base_topic}/").removesuffix("/availability")
        payload = _parse_json(msg.topic, msg.payload)
        state = payload.get("state") if isinstance(payload, dict) else msg.payload
        if state not in ("online", "offline"):
            return

        ieee_address = next(
            (d.ieee_address for d in self.devices.values() if d.friendly_name == friendly_name),
            None,
        )
        if ieee_address is None:
            return

        previous = self._device_availability.get(ieee_address)
        # Only reset "since" on an actual transition - Z2M can republish the
        # same retained state repeatedly, and resetting on every republish
        # would make "how long has this device been offline" always show
        # ~0, defeating the point of tracking it.
        if previous is not None and previous.state == state:
            since = previous.since
        else:
            since = dt_util.utcnow()
        self._device_availability[ieee_address] = DeviceAvailability(state=state, since=since)
        async_dispatcher_send(
            self.hass,
            signal_device_availability(self.entry_id, ieee_address),
            self._device_availability[ieee_address],
        )
        async_dispatcher_send(self.hass, signal_offline_candidates_changed(self.entry_id), None)

    @callback
    def _handle_bridge_groups(self, msg: mqtt.ReceiveMessage) -> None:
        payload = _parse_json(msg.topic, msg.payload)
        if payload is None:
            return

        groups: dict[int, Z2MGroup] = {}
        for item in payload:
            group_id = item.get("id")
            if group_id is None:
                continue
            groups[group_id] = Z2MGroup(
                id=group_id,
                friendly_name=item.get("friendly_name", str(group_id)),
                members=item.get("members", []),
            )
        self.groups = groups
        async_dispatcher_send(self.hass, signal_bridge_groups(self.entry_id), self.groups)

    @callback
    def _handle_bridge_response(self, msg: mqtt.ReceiveMessage) -> None:
        prefix = f"{self.base_topic}/bridge/response/"
        command = msg.topic.removeprefix(prefix)

        payload = _parse_json(msg.topic, msg.payload)
        if payload is None:
            return

        transaction = payload.get("transaction")
        future = self._pending.get((command, transaction))
        if future is None or future.done():
            # Expected for retained/duplicate deliveries, responses to requests
            # we already timed out on, or transactions sent by something else
            # entirely (e.g. the Zigbee2MQTT frontend) - not an error.
            #
            # networkmap is the one exception: on a large mesh (especially
            # with routes=true) it can take longer than even
            # REQUEST_TIMEOUT_NETWORKMAP to respond, and the data is still
            # worth applying once it finally arrives even though the
            # original request (and the button press awaiting it) already
            # timed out - otherwise the networkmap sensor is stuck at
            # "unknown" forever despite Zigbee2MQTT actually responding.
            if future is None and command == CMD_NETWORKMAP and payload.get("status") == "ok":
                _LOGGER.info(
                    "Applying a Zigbee2MQTT networkmap response that arrived after "
                    "its request had already timed out (transaction=%s) - consider "
                    "raising REQUEST_TIMEOUT_NETWORKMAP if this happens often",
                    transaction,
                )
                self._apply_networkmap_data(payload.get("data", {}))
            else:
                _LOGGER.debug(
                    "Discarding unmatched bridge response for '%s' (transaction=%s)",
                    command,
                    transaction,
                )
            return
        future.set_result(payload)


def _parse_json(topic: str, raw_payload: Any) -> Any | None:
    """Best-effort JSON parse, logging and returning None on failure."""
    try:
        return json.loads(raw_payload)
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid JSON payload on %s", topic)
        return None


def _parse_last_seen(value: Any) -> datetime | None:
    """Parse a device's last_seen field, however Z2M's advanced.last_seen is configured.

    Z2M can be set to omit it (None), or to emit ISO 8601 / ISO 8601 local
    (str) or epoch seconds (int/float) - handle all of these.

    Must always return a timezone-aware datetime: the "local" string format
    has no UTC offset and parses as naive, and comparing a naive datetime
    against dt_util.utcnow() in compute_offline_devices() raises TypeError
    ("can't subtract offset-naive and offset-aware datetimes"). That
    exception used to propagate out of the offline-devices sensor's
    native_value, leaving it stuck at "unknown" indefinitely - since the
    sensor never gets to call async_write_ha_state() successfully, nothing
    short of restarting Zigbee2MQTT (and getting lucky that the next
    payload happens not to trigger it) would clear it.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Z2M's "epoch" advanced.last_seen format is seconds since 1970, not
        # milliseconds, despite that being the more common JS convention.
        return dt_util.utc_from_timestamp(value)
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        # as_local treats a naive value as already being in HA's configured
        # local timezone, which is exactly what "ISO_8601_local" means.
        return dt_util.as_local(parsed) if parsed is not None else None
    return None
