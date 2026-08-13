"""Tests for the light proxy."""

from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desired_state.const import (
    ATTR_DESIRED_BRIGHTNESS,
    ATTR_PENDING,
    ATTR_SOURCE_ENTITY,
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    OPT_DESIRED_BRIGHTNESS,
    OPT_DESIRED_ON,
    PROXY_TYPE_AUTO,
    PROXY_TYPE_LIGHT,
)

from .conftest import (
    SOURCE_LIGHT,
    SOURCE_SWITCH,
    build_entry,
    calls_to_source,
    set_source,
    setup_entry,
)

LIGHT_PROXY_ENTITY_ID = "light.test_light_proxy"
SWITCH_SOURCE_PROXY_ENTITY_ID = "light.test_proxy"


async def call_proxy(
    hass: HomeAssistant, entity_id: str, service: str, **data: object
) -> None:
    """Call a light service on the proxy entity."""
    await hass.services.async_call(
        "light", service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_light_proxy_from_switch_source(
    hass: HomeAssistant, mock_switch_source: str, service_calls: list[Event]
) -> None:
    """A light proxy on a switch source only exposes on/off."""
    entry = build_entry(source_entity=mock_switch_source, proxy_type=PROXY_TYPE_LIGHT)
    await setup_entry(hass, entry)

    state = hass.states.get(SWITCH_SOURCE_PROXY_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_SUPPORTED_COLOR_MODES] == [ColorMode.ONOFF]
    assert state.attributes.get(ATTR_BRIGHTNESS) is None
    assert state.attributes[ATTR_SOURCE_ENTITY] == SOURCE_SWITCH

    await call_proxy(hass, SWITCH_SOURCE_PROXY_ENTITY_ID, SERVICE_TURN_ON)

    calls = calls_to_source(service_calls, SOURCE_SWITCH, SERVICE_TURN_ON)
    assert len(calls) == 1
    assert ATTR_BRIGHTNESS not in calls[0]
    assert hass.states.get(SWITCH_SOURCE_PROXY_ENTITY_ID).state == STATE_ON


async def test_light_proxy_from_light_source(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry
) -> None:
    """A light proxy on a light source mirrors the source capabilities."""
    await setup_entry(hass, light_proxy_entry)

    state = hass.states.get(LIGHT_PROXY_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert set(state.attributes[ATTR_SUPPORTED_COLOR_MODES]) == {
        ColorMode.COLOR_TEMP,
        ColorMode.RGB,
    }
    assert state.attributes[ATTR_SOURCE_ENTITY] == SOURCE_LIGHT


async def test_turn_on_with_brightness(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Turning on with brightness forwards the brightness to the source."""
    await setup_entry(hass, light_proxy_entry)
    service_calls.clear()

    await call_proxy(
        hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 128}
    )

    calls = calls_to_source(service_calls, SOURCE_LIGHT, SERVICE_TURN_ON)
    assert len(calls) == 1
    assert calls[0][ATTR_BRIGHTNESS] == 128

    state = hass.states.get(LIGHT_PROXY_ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128
    assert state.attributes[ATTR_DESIRED_BRIGHTNESS] == 128


async def test_turn_on_with_color_temp_and_rgb(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Color temperature and rgb color are remembered and forwarded."""
    await setup_entry(hass, light_proxy_entry)
    service_calls.clear()

    await call_proxy(
        hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_ON, **{ATTR_COLOR_TEMP_KELVIN: 4000}
    )
    calls = calls_to_source(service_calls, SOURCE_LIGHT, SERVICE_TURN_ON)
    assert calls[-1][ATTR_COLOR_TEMP_KELVIN] == 4000
    assert hass.states.get(LIGHT_PROXY_ENTITY_ID).attributes[ATTR_COLOR_TEMP_KELVIN] == 4000

    await call_proxy(
        hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_ON, **{ATTR_RGB_COLOR: (10, 20, 30)}
    )
    calls = calls_to_source(service_calls, SOURCE_LIGHT, SERVICE_TURN_ON)
    assert list(calls[-1][ATTR_RGB_COLOR]) == [10, 20, 30]
    assert hass.states.get(LIGHT_PROXY_ENTITY_ID).attributes[ATTR_RGB_COLOR] == (10, 20, 30)


async def test_turn_on_unavailable_remembers_brightness(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """While the source is offline the light parameters are remembered."""
    await setup_entry(hass, light_proxy_entry)
    set_source(hass, SOURCE_LIGHT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    service_calls.clear()

    await call_proxy(
        hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 200}
    )

    assert not calls_to_source(service_calls, SOURCE_LIGHT)
    state = hass.states.get(LIGHT_PROXY_ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 200
    assert state.attributes[ATTR_PENDING] is True
    assert light_proxy_entry.options[OPT_DESIRED_ON] is True
    assert light_proxy_entry.options[OPT_DESIRED_BRIGHTNESS] == 200


async def test_source_returns_applies_remembered_brightness(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """When the source comes back the remembered parameters are applied."""
    await setup_entry(hass, light_proxy_entry)
    set_source(hass, SOURCE_LIGHT, STATE_UNAVAILABLE)
    await hass.async_block_till_done()

    await call_proxy(
        hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 77}
    )
    service_calls.clear()

    set_source(hass, SOURCE_LIGHT, STATE_OFF)
    await hass.async_block_till_done()

    calls = calls_to_source(service_calls, SOURCE_LIGHT, SERVICE_TURN_ON)
    assert len(calls) == 1
    assert calls[0][ATTR_BRIGHTNESS] == 77

    service_calls.clear()
    set_source(hass, SOURCE_LIGHT, STATE_ON, {ATTR_BRIGHTNESS: 77})
    await hass.async_block_till_done()

    assert not calls_to_source(service_calls, SOURCE_LIGHT)
    assert hass.states.get(LIGHT_PROXY_ENTITY_ID).attributes[ATTR_PENDING] is False


async def test_turn_off_light_proxy(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry, service_calls: list[Event]
) -> None:
    """Turning off the proxy turns off the source."""
    set_source(hass, SOURCE_LIGHT, STATE_ON, {ATTR_BRIGHTNESS: 255})
    await setup_entry(hass, light_proxy_entry)
    service_calls.clear()

    await call_proxy(hass, LIGHT_PROXY_ENTITY_ID, SERVICE_TURN_OFF)

    assert len(calls_to_source(service_calls, SOURCE_LIGHT, SERVICE_TURN_OFF)) == 1
    assert hass.states.get(LIGHT_PROXY_ENTITY_ID).state == STATE_OFF


async def test_no_proxy_chains(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry
) -> None:
    """A proxy entity cannot be used as the source of another proxy."""
    await setup_entry(hass, light_proxy_entry)
    assert hass.states.get(LIGHT_PROXY_ENTITY_ID) is not None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE_ENTITY: LIGHT_PROXY_ENTITY_ID,
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_PROXY_NAME: "Chained",
            CONF_HIDE_SOURCE: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SOURCE_ENTITY: "proxy_chain"}


async def test_no_duplicate_proxies(
    hass: HomeAssistant, light_proxy_entry: MockConfigEntry
) -> None:
    """The same source entity cannot be proxied twice."""
    await setup_entry(hass, light_proxy_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SOURCE_ENTITY: SOURCE_LIGHT,
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_PROXY_NAME: "Duplicate",
            CONF_HIDE_SOURCE: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SOURCE_ENTITY: "already_proxied"}
