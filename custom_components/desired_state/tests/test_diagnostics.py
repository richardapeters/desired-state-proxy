"""Tests for diagnostics and reconciliation retries."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desired_state.const import (
    RECONCILE_MAX_ATTEMPTS,
    RECONCILE_RETRY_DELAY,
)
from custom_components.desired_state.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SOURCE_SWITCH, calls_to_source, set_source, setup_entry

PROXY_ENTITY_ID = "switch.test_proxy"


async def test_diagnostics(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry
) -> None:
    """Diagnostics contain proxy, source and sync information."""
    await setup_entry(hass, switch_proxy_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, switch_proxy_entry)

    assert diagnostics["source"]["entity_id"] == SOURCE_SWITCH
    assert diagnostics["source"]["state"] == STATE_OFF
    assert diagnostics["coordinator"]["desired_state"] == STATE_OFF
    assert diagnostics["coordinator"]["in_sync"] is True
    assert diagnostics["sync"] == {"in_sync": True, "pending": False}
    assert diagnostics["proxy"]["entities"][0]["entity_id"] == PROXY_ENTITY_ID

    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, switch_proxy_entry)
    assert diagnostics["source"]["available"] is False
    assert diagnostics["sync"]["pending"] is True


async def test_reconcile_retries_when_source_does_not_follow(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """A retry is scheduled when the source does not reach the desired state."""
    await setup_entry(hass, switch_proxy_entry)
    service_calls.clear()

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: PROXY_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)) == 1

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=RECONCILE_RETRY_DELAY + 1)
    )
    await hass.async_block_till_done()

    assert len(calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)) == 2

    set_source(hass, SOURCE_SWITCH, STATE_ON)
    await hass.async_block_till_done()
    service_calls.clear()

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=RECONCILE_RETRY_DELAY + 1)
    )
    await hass.async_block_till_done()

    assert not calls_to_source(service_calls, SOURCE_SWITCH)


async def test_reconcile_gives_up_after_max_attempts(
    hass: HomeAssistant, switch_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Reconciliation stops after the maximum number of attempts."""
    await setup_entry(hass, switch_proxy_entry)
    service_calls.clear()

    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {ATTR_ENTITY_ID: PROXY_ENTITY_ID}, blocking=True
    )
    await hass.async_block_till_done()

    for _ in range(RECONCILE_MAX_ATTEMPTS + 2):
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=RECONCILE_RETRY_DELAY + 1)
        )
        await hass.async_block_till_done()

    calls = calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)
    assert len(calls) == RECONCILE_MAX_ATTEMPTS

    # A source state change that keeps it out of sync must not restart the loop.
    set_source(hass, SOURCE_SWITCH, STATE_OFF, {"extra": 1})
    await hass.async_block_till_done()
    assert len(calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)) == (
        RECONCILE_MAX_ATTEMPTS
    )

    # Coming back from unavailable does allow a fresh attempt.
    set_source(hass, SOURCE_SWITCH, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    set_source(hass, SOURCE_SWITCH, STATE_OFF)
    await hass.async_block_till_done()
    assert len(calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)) == (
        RECONCILE_MAX_ATTEMPTS + 1
    )
