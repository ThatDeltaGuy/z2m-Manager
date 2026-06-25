"""Tests for Z2MLinkedDeviceEntity's entity_id naming.

Covers a real production bug: newer HA Core (see entity_platform's
_async_derive_object_ids and entity_registry's _async_get_full_entity_name)
treats a value read from the suggested_object_id *property* as a mere
"object_id_base", which the registry then re-combines with the device's
(and, if assigned, its area's) name a second time - producing entity_ids
like "bedroom_bedroom_light_1_bedroom_light_1_image" for a device named
"Bedroom Light 1" in a "Bedroom" area, instead of "bedroom_light_1_image".
internal_integration_suggested_object_id is the newer attribute that bypasses
that re-combination; suggested_object_id is kept for older HA Core that
doesn't read the newer attribute at all. Both are one-line delegations to
_device_prefixed_suggestion, tested directly here - that's the only part
safe to call outside of a real entity_platform registration flow (the
properties themselves need self.platform set, which isn't available until
an entity has actually been added to a platform).

This package's pinned HA Core test dependency (2025.1.4, see
requirements-test.txt) predates the newer registry behavior, so it cannot
exercise the actual double-prefixing bug end-to-end - these tests instead
pin down the one piece of logic both code paths share.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.zigbee2mqtt_manager.button import Z2MRemoveDeviceButton

from .conftest import FRIENDLY_NAME, IEEE_ADDRESS


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_suggestion_properties_prefix_device_name_exactly_once(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    entry, target_device = linked_setup
    hub = entry.runtime_data

    button = Z2MRemoveDeviceButton(hub, IEEE_ADDRESS, target_device.id)

    result = button._device_prefixed_suggestion("Remove device")
    assert result == f"{FRIENDLY_NAME} Remove device"
    # Must never be prefixed twice, regardless of which one a given HA Core
    # version actually consults.
    assert result.count(FRIENDLY_NAME) == 1


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_suggestion_falls_back_to_bare_name_without_device(
    hass: HomeAssistant, mqtt_mock, linked_setup
) -> None:
    """No device_entry (e.g. the device was removed) must not crash - just
    fall back to the entity's own bare suggestion, unprefixed.
    """
    entry, target_device = linked_setup
    hub = entry.runtime_data

    button = Z2MRemoveDeviceButton(hub, IEEE_ADDRESS, target_device.id)
    button.device_entry = None

    assert button._device_prefixed_suggestion("Remove device") == "Remove device"
