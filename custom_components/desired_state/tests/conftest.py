"""Fixtures for the Desired State Proxy tests."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    EVENT_CALL_SERVICE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.desired_state.const import (
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    PROXY_TYPE_LIGHT,
    PROXY_TYPE_SWITCH,
)

SOURCE_SWITCH = "switch.test_source"
SOURCE_LIGHT = "light.test_source"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable loading of custom integrations in all tests."""
    return


@pytest.fixture
async def mock_switch_source(hass: HomeAssistant) -> str:
    """Register a mock switch source entity that is off."""
    assert await async_setup_component(hass, "switch", {})
    await hass.async_block_till_done()
    hass.states.async_set(SOURCE_SWITCH, STATE_OFF, {"friendly_name": "Test Source"})
    return SOURCE_SWITCH


@pytest.fixture
async def mock_light_source(hass: HomeAssistant) -> str:
    """Register a mock light source entity."""
    assert await async_setup_component(hass, "light", {})
    await hass.async_block_till_done()
    hass.states.async_set(
        SOURCE_LIGHT,
        STATE_OFF,
        {
            "friendly_name": "Test Light",
            "supported_color_modes": [ColorMode.COLOR_TEMP, ColorMode.RGB],
            ATTR_SUPPORTED_FEATURES: 0,
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6535,
        },
    )
    return SOURCE_LIGHT


def build_entry(
    *,
    source_entity: str,
    proxy_type: str,
    name: str = "Test Proxy",
    hide_source: bool = False,
    options: dict[str, Any] | None = None,
) -> MockConfigEntry:
    """Create a mock config entry for the integration."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=f"{DOMAIN}_{source_entity}",
        data={
            CONF_SOURCE_ENTITY: source_entity,
            CONF_PROXY_TYPE: proxy_type,
            CONF_PROXY_NAME: name,
            CONF_HIDE_SOURCE: hide_source,
        },
        options=options or {},
    )


@pytest.fixture
def switch_proxy_entry(mock_switch_source: str) -> MockConfigEntry:
    """Return a config entry proxying a switch as a switch."""
    return build_entry(source_entity=mock_switch_source, proxy_type=PROXY_TYPE_SWITCH)


@pytest.fixture
def light_proxy_entry(mock_light_source: str) -> MockConfigEntry:
    """Return a config entry proxying a light as a light."""
    return build_entry(
        source_entity=mock_light_source, proxy_type=PROXY_TYPE_LIGHT, name="Test Light Proxy"
    )

async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> MockConfigEntry:
    """Add and set up a config entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def set_source(
    hass: HomeAssistant, entity_id: str, state: str, attributes: dict[str, Any] | None = None
) -> None:
    """Set the state of a source entity, preserving its attributes."""
    current = hass.states.get(entity_id)
    merged = dict(current.attributes) if current is not None else {}
    if attributes:
        merged.update(attributes)
    hass.states.async_set(entity_id, state, merged)


@pytest.fixture
def service_calls(hass: HomeAssistant) -> list[Event]:
    """Capture all service call events."""
    return async_capture_events(hass, EVENT_CALL_SERVICE)


def calls_to_source(
    events: list[Event], source_entity_id: str, service: str | None = None
) -> list[dict[str, Any]]:
    """Return the service data of calls targeting the source entity."""
    result: list[dict[str, Any]] = []
    for event in events:
        data = event.data.get("service_data") or {}
        entity_id = data.get(ATTR_ENTITY_ID)
        entity_ids = [entity_id] if isinstance(entity_id, str) else list(entity_id or [])
        if source_entity_id not in entity_ids:
            continue
        if service is not None and event.data.get("service") != service:
            continue
        result.append(data)
    return result


__all__ = [
    "SOURCE_LIGHT",
    "SOURCE_SWITCH",
    "STATE_OFF",
    "STATE_ON",
    "build_entry",
    "calls_to_source",
    "set_source",
    "setup_entry",
]
