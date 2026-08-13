"""Tests for the switch proxy."""

from __future__ import annotations

import pytest
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import Event, HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.desired_state.const import (
    ATTR_ACTUAL_STATE,
    ATTR_DESIRED_STATE,
    ATTR_PENDING,
    ATTR_SOURCE_ENTITY,
    OPT_DESIRED_ON,
    PROXY_TYPE_SWITCH,
)

from .conftest import (
    SOURCE_SWITCH,
    build_entry,
    calls_to_source,
    set_source,
    setup_entry,
)

PROXY_ENTITY_ID = "switch.test_proxy"


def source_calls(events: list[Event], service: str | None = None) -> list[dict]:
    """Return service calls targeting the source switch."""
    return calls_to_source(events, SOURCE_SWITCH, service)


async def call_proxy(hass: HomeAssistant, service: str) -> None:
    """Call a service on the proxy entity."""
    await hass.services.async_call(
        "switch", service, {ATTR_ENTITY_ID: PROXY_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()


async def test_switch_proxy_created(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """The proxy entity is created and exposes the desired state attributes."""
    await setup_entry(hass, switch_proxy_entry)

    state = hass.states.get(PROXY_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_SOURCE_ENTITY] == SOURCE_SWITCH
    assert state.attributes[ATTR_DESIRED_STATE] == STATE_OFF
    assert state.attributes[ATTR_ACTUAL_STATE] == STATE_OFF
    assert state.attributes[ATTR_PENDING] is False
    assert not source_calls(service_calls)


async def test_turn_on_source_available(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Turning on the proxy forwards the command to the source entity."""
    await setup_entry(hass, switch_proxy_entry)

    await call_proxy(hass, SERVICE_TURN_ON)

    assert hass.states.get(PROXY_ENTITY_ID).state == STATE_ON
    assert len(source_calls(service_calls, SERVICE_TURN_ON)) == 1

    set_source(hass, SOURCE_SWITCH, STATE_ON)
    await hass.async_block_till_done()
    assert hass.states.get(PROXY_ENTITY_ID).attributes[ATTR_PENDING] is False


async def test_turn_off_source_available(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Turning off the proxy forwards the command to the source entity."""
    set_source(hass, SOURCE_SWITCH, STATE_ON)
    await setup_entry(hass, switch_proxy_entry)
    service_calls.clear()

    await call_proxy(hass, SERVICE_TURN_OFF)

    assert hass.states.get(PROXY_ENTITY_ID).state == STATE_OFF
    assert len(source_calls(service_calls, SERVICE_TURN_OFF)) == 1


async def test_turn_on_source_unavailable(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """The proxy stays available and records the desired state when source is offline."""
    await setup_entry(hass, switch_proxy_entry)
    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    service_calls.clear()

    await call_proxy(hass, SERVICE_TURN_ON)

    state = hass.states.get(PROXY_ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PENDING] is True
    assert state.attributes[ATTR_ACTUAL_STATE] == STATE_UNAVAILABLE
    assert not source_calls(service_calls)


async def test_turn_off_source_unavailable(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Turning off while the source is offline only updates the desired state."""
    set_source(hass, SOURCE_SWITCH, STATE_ON)
    await setup_entry(hass, switch_proxy_entry)
    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    service_calls.clear()

    await call_proxy(hass, SERVICE_TURN_OFF)

    state = hass.states.get(PROXY_ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_PENDING] is True
    assert not source_calls(service_calls)


async def test_reconcile_when_source_returns(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """When the source returns out of sync, the desired state is pushed to it."""
    await setup_entry(hass, switch_proxy_entry)
    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    await call_proxy(hass, SERVICE_TURN_ON)
    service_calls.clear()

    set_source(hass, SOURCE_SWITCH, STATE_OFF)
    await hass.async_block_till_done()

    calls = source_calls(service_calls, SERVICE_TURN_ON)
    assert len(calls) == 1
    assert calls[0][ATTR_ENTITY_ID] == SOURCE_SWITCH


async def test_no_command_when_already_in_sync(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """No command is sent when the source already matches the desired state."""
    await setup_entry(hass, switch_proxy_entry)
    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    await call_proxy(hass, SERVICE_TURN_ON)
    service_calls.clear()

    set_source(hass, SOURCE_SWITCH, STATE_ON)
    await hass.async_block_till_done()

    assert not source_calls(service_calls)
    state = hass.states.get(PROXY_ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_PENDING] is False


async def test_desired_state_persisted_in_options(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry
) -> None:
    """The desired state is persisted in the config entry options."""
    await setup_entry(hass, switch_proxy_entry)

    await call_proxy(hass, SERVICE_TURN_ON)
    assert switch_proxy_entry.options[OPT_DESIRED_ON] is True

    await call_proxy(hass, SERVICE_TURN_OFF)
    assert switch_proxy_entry.options[OPT_DESIRED_ON] is False


@pytest.mark.parametrize("desired_on", [True, False])
async def test_desired_state_restored_after_restart(
    hass: HomeAssistant, mock_switch_source: str, desired_on: bool
) -> None:
    """A restart restores the desired state from the config entry options."""
    entry = build_entry(
        source_entity=mock_switch_source,
        proxy_type=PROXY_TYPE_SWITCH,
        options={OPT_DESIRED_ON: desired_on},
    )
    set_source(hass, SOURCE_SWITCH, STATE_ON if desired_on else STATE_OFF)
    await setup_entry(hass, entry)

    state = hass.states.get(PROXY_ENTITY_ID)
    assert state.state == (STATE_ON if desired_on else STATE_OFF)
    assert state.attributes[ATTR_PENDING] is False


async def test_reconcile_on_setup_when_out_of_sync(
    hass: HomeAssistant, mock_switch_source: str, service_calls: list[Event]
) -> None:
    """A stored desired state is applied to the source when the proxy is set up."""
    entry = build_entry(
        source_entity=mock_switch_source,
        proxy_type=PROXY_TYPE_SWITCH,
        options={OPT_DESIRED_ON: True},
    )
    set_source(hass, SOURCE_SWITCH, STATE_OFF)

    await setup_entry(hass, entry)

    assert len(source_calls(service_calls, SERVICE_TURN_ON)) >= 1


async def test_unload_entry(hass: HomeAssistant, switch_proxy_entry: MockConfigEntry) -> None:
    """Unloading the entry removes the proxy from operation."""
    await setup_entry(hass, switch_proxy_entry)
    assert hass.states.get(PROXY_ENTITY_ID).state == STATE_OFF

    assert await hass.config_entries.async_unload(switch_proxy_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(PROXY_ENTITY_ID).state == STATE_UNAVAILABLE


async def test_desired_state_restored_from_entity_state(
    hass: HomeAssistant, mock_switch_source: str
) -> None:
    """Without persisted options the desired state is restored from the entity state."""
    mock_restore_cache(hass, [State(PROXY_ENTITY_ID, STATE_ON)])

    entry = build_entry(source_entity=mock_switch_source, proxy_type=PROXY_TYPE_SWITCH)
    await setup_entry(hass, entry)

    assert hass.states.get(PROXY_ENTITY_ID).state == STATE_ON
    assert entry.options[OPT_DESIRED_ON] is True
