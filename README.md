# Zigbee2MQTT Manager

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

A Home Assistant custom integration that acts as a management layer in front of one or more [Zigbee2MQTT](https://www.zigbee2mqtt.io/) instances, talking purely over MQTT.

## What this does

- **Bridge-level control and status** for each configured Zigbee2MQTT instance: online/offline, version and network info, restart, permit-join, log level, and configured groups.
- **Network map sensor** - refreshable on demand or on a configurable interval, with the parsed topology as attributes (a native equivalent of the `zigbee2mqtt/bridge/response/networkmap` MQTT-template sensor many users build by hand), and its last result restored across Home Assistant restarts.
- **Offline devices, battery-low, low-link-quality, and OTA-available sensors** - each lists the affected devices (name plus the relevant metric), with configurable thresholds where applicable. Detection for offline devices auto-switches per device between Zigbee2MQTT's `/availability` topic and a `last_seen` threshold.
- **OTA update tooling at the bridge level**: a "check for firmware updates" button that sweeps every device, an automatic check interval (configurable, off by default), and `ota_check`/`ota_update` services for automations. There's no per-device OTA update entity - Zigbee2MQTT's own MQTT discovery already provides one.
- **Per-device extras** attached to the *same* Home Assistant device that Zigbee2MQTT's own MQTT discovery already created for that Zigbee device, never a duplicate:
  - **Remove** and **re-interview** buttons.
  - These only appear once Home Assistant already has a device for it via discovery, and disappear again automatically if that ever stops being true - without restarting Home Assistant.
- **Services** for renaming/removing/re-interviewing devices, permit-join (network-wide or scoped to one router), restart, bridge options, OTA check/install, network map refresh, and a generic raw bridge-command passthrough (`raw_command`) for anything not given dedicated UI, such as touchlink or group management.
- **Multiple Zigbee2MQTT instances**, each as its own config entry, sharing the one MQTT broker Home Assistant's core `mqtt` integration is connected to, distinguished by each instance's `base_topic`.
- **Diagnostics** for each config entry, including the device-linking cache, useful when troubleshooting why a device's extras aren't appearing.

## What this does NOT do

- It does **not** create lights, sensors, switches, etc. for your Zigbee devices - those already come from Zigbee2MQTT's own MQTT discovery via Home Assistant's core `mqtt` integration. If you don't see those, check Zigbee2MQTT's `homeassistant` (discovery) setting, not this integration.
- It does **not** create a per-device OTA update entity, for the same reason - Zigbee2MQTT's own discovery already provides one. This integration's OTA tooling (button, automatic check, services, and the OTA-available sensor) is bridge-level instead.
- It does **not** create a duplicate device for a Zigbee device that's already been discovered. If discovery is off for a device (or Home Assistant just hasn't picked it up yet), you'll still get all the bridge-level features, just not that device's per-device extras until discovery catches up.
- It does **not** support multiple MQTT brokers - all configured instances share the single broker Home Assistant's `mqtt` integration connects to (matching how that integration itself works).

## Requirements

- Home Assistant's core **MQTT** integration must already be set up and connected.
- Each Zigbee2MQTT instance you add should have a distinct `mqtt.base_topic` (the default `zigbee2mqtt` for the first instance, e.g. `zigbee2mqtt_2` for a second).

## Installation

### HACS (custom repository)

1. HACS -> the three-dot menu -> **Custom repositories** -> add this repository's URL, category **Integration**.
2. Install **Zigbee2MQTT Manager**, then restart Home Assistant.
3. Settings -> Devices & Services -> **Add Integration** -> search for "Zigbee2MQTT Manager", or click the badge below if Home Assistant is reachable from this browser:

   [![Add Integration][add-integration-badge]][add-integration]

### Manual

Copy `custom_components/zigbee2mqtt_manager` into your Home Assistant `custom_components` directory and restart.

## Configuration

Setup asks for an instance name and the Zigbee2MQTT instance's MQTT base topic. Everything else is tunable afterwards via the integration's **Configure** options:

| Option | Default | Notes |
|---|---|---|
| Offline threshold | 15 minutes | Fallback only, for devices with no `/availability` topic |
| Network map refresh interval | 60 minutes | `0` disables automatic refresh (on-demand via button/service still works) |
| Network map type | `raw` | Only `raw` produces structured attributes; `graphviz`/`plantuml` return a text graph |
| Network map routes | off | Adds active route info, at the cost of a slower refresh |
| Default permit-join duration | 254 seconds | Used when the permit-join switch is turned on |

## Services

| Service | Purpose |
|---|---|
| `zigbee2mqtt_manager.rename_device` | Rename a linked device |
| `zigbee2mqtt_manager.remove_device` | Remove a device (`force`/`block` options) |
| `zigbee2mqtt_manager.reinterview_device` | Force a re-interview |
| `zigbee2mqtt_manager.permit_join` | Permit join, network-wide or scoped to one router |
| `zigbee2mqtt_manager.restart` | Restart a Zigbee2MQTT instance |
| `zigbee2mqtt_manager.set_options` | Update Zigbee2MQTT's runtime options |
| `zigbee2mqtt_manager.ota_check` | Check for a firmware update without installing it |
| `zigbee2mqtt_manager.ota_update` | Install an available firmware update |
| `zigbee2mqtt_manager.refresh_networkmap` | Refresh the network map, optionally overriding type/routes |
| `zigbee2mqtt_manager.raw_command` | Publish any `bridge/request/<command>` and return its response |

## FAQ

**Why don't I see light/sensor/switch entities for my Zigbee devices from this integration?**
Those come from Zigbee2MQTT's own MQTT discovery (the `homeassistant` setting in Zigbee2MQTT's configuration), consumed by Home Assistant's core `mqtt` integration. This integration deliberately doesn't duplicate them - it only adds bridge-level controls and a small set of per-device extras Zigbee2MQTT's discovery doesn't provide.

**Why doesn't a device have its remove / re-interview buttons?**
Those attach to the Home Assistant device Zigbee2MQTT's own discovery created. If that device doesn't exist yet (discovery disabled in Zigbee2MQTT, or Home Assistant hasn't picked it up yet), this integration intentionally skips creating extras for it rather than making a duplicate device. Enable discovery for that device in Zigbee2MQTT and the extras will appear automatically. The integration's diagnostics (Settings -> Devices & Services -> Zigbee2MQTT Manager -> Download diagnostics) show the current device-linking state if you need to check why.

**How do I reach a Zigbee2MQTT bridge command this integration doesn't have a button/switch for (e.g. touchlink, group management)?**
Use the `zigbee2mqtt_manager.raw_command` service, which publishes any `bridge/request/<command>` payload you give it and returns the response.

## Development

Tests use `pytest` + `pytest-homeassistant-custom-component` (`pip install -r requirements-test.txt`, then `pytest tests/`). Linting/formatting use `ruff` (`ruff check custom_components tests` / `ruff format custom_components tests`). CI runs both, plus `hassfest` and the HACS validation action, on every push and pull request.

## License

[GPL-3.0](LICENSE.md)

[commits-shield]: https://img.shields.io/github/commit-activity/w/ThatDeltaGuy/z2m-Manager?style=for-the-badge
[commits]: https://github.com/ThatDeltaGuy/z2m-Manager/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license]: LICENSE.md
[license-shield]: https://img.shields.io/github/license/ThatDeltaGuy/z2m-Manager.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40ThatDeltaGuy-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/ThatDeltaGuy/z2m-Manager.svg?style=for-the-badge
[releases]: https://github.com/ThatDeltaGuy/z2m-Manager/releases
[user_profile]: https://github.com/ThatDeltaGuy
[add-integration]: https://my.home-assistant.io/redirect/config_flow_start?domain=zigbee2mqtt_manager
[add-integration-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
