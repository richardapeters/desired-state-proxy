"""Tests for the Desired State Proxy config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.desired_state.const import (
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    PROXY_TYPE_AUTO,
    PROXY_TYPE_LIGHT,
    PROXY_TYPE_SWITCH,
)

from .conftest import SOURCE_LIGHT, SOURCE_SWITCH, build_entry, setup_entry


async def start_flow(hass: HomeAssistant, user_input: dict) -> dict:
    """Start and complete one iteration of the user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_config_flow_switch_source(
    hass: HomeAssistant, mock_switch_source: str
) -> None:
    """A basic config flow creates an entry with resolved settings."""
    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE_SWITCH,
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_PROXY_NAME: "Kitchen Desired",
            CONF_HIDE_SOURCE: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kitchen Desired"
    assert result["data"] == {
        CONF_SOURCE_ENTITY: SOURCE_SWITCH,
        CONF_PROXY_TYPE: PROXY_TYPE_SWITCH,
        CONF_PROXY_NAME: "Kitchen Desired",
        CONF_HIDE_SOURCE: False,
    }
    assert hass.states.get("switch.kitchen_desired") is not None


async def test_config_flow_auto_light(hass: HomeAssistant, mock_light_source: str) -> None:
    """A light source resolves to a light proxy in automatic mode."""
    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE_LIGHT,
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_HIDE_SOURCE: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROXY_TYPE] == PROXY_TYPE_LIGHT
    assert result["data"][CONF_PROXY_NAME] == "Test Light Desired"
    assert hass.states.get("light.test_light_desired") is not None


async def test_config_flow_switch_type_rejects_light_source(
    hass: HomeAssistant, mock_light_source: str
) -> None:
    """A switch proxy cannot proxy a light source."""
    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE_LIGHT,
            CONF_PROXY_TYPE: PROXY_TYPE_SWITCH,
            CONF_HIDE_SOURCE: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROXY_TYPE: "invalid_proxy_type"}


async def test_config_flow_light_type_accepts_switch_source(
    hass: HomeAssistant, mock_switch_source: str
) -> None:
    """A light proxy may proxy a switch source."""
    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE_SWITCH,
            CONF_PROXY_TYPE: PROXY_TYPE_LIGHT,
            CONF_PROXY_NAME: "Switch As Light",
            CONF_HIDE_SOURCE: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROXY_TYPE] == PROXY_TYPE_LIGHT
    assert hass.states.get("light.switch_as_light") is not None


async def test_config_flow_duplicate_source_rejected(
    hass: HomeAssistant, mock_switch_source: str
) -> None:
    """An already proxied entity cannot be proxied again."""
    entry = build_entry(source_entity=SOURCE_SWITCH, proxy_type=PROXY_TYPE_SWITCH)
    await setup_entry(hass, entry)

    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: SOURCE_SWITCH,
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_HIDE_SOURCE: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SOURCE_ENTITY: "already_proxied"}


async def test_config_flow_proxy_chain_rejected(
    hass: HomeAssistant, mock_switch_source: str
) -> None:
    """A proxy entity of this integration cannot be used as source."""
    entry = build_entry(source_entity=SOURCE_SWITCH, proxy_type=PROXY_TYPE_SWITCH)
    await setup_entry(hass, entry)
    assert hass.states.get("switch.test_proxy") is not None

    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: "switch.test_proxy",
            CONF_PROXY_TYPE: PROXY_TYPE_AUTO,
            CONF_HIDE_SOURCE: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SOURCE_ENTITY: "proxy_chain"}


async def test_config_flow_hide_source(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Hiding the source is applied and reverted on removal."""
    assert await async_setup_component(hass, "switch", {})
    await hass.async_block_till_done()

    source_entry = entity_registry.async_get_or_create(
        "switch", "test", "abc", suggested_object_id="hideable"
    )
    source_entity_id = source_entry.entity_id
    hass.states.async_set(source_entity_id, STATE_OFF)

    result = await start_flow(
        hass,
        {
            CONF_SOURCE_ENTITY: source_entity_id,
            CONF_PROXY_TYPE: PROXY_TYPE_SWITCH,
            CONF_PROXY_NAME: "Hidden Proxy",
            CONF_HIDE_SOURCE: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entity_registry.async_get(source_entity_id).hidden_by is er.RegistryEntryHider.INTEGRATION

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(source_entity_id).hidden_by is None


async def test_options_flow(hass: HomeAssistant, mock_switch_source: str) -> None:
    """The options flow updates the proxy name."""
    entry = build_entry(source_entity=SOURCE_SWITCH, proxy_type=PROXY_TYPE_SWITCH)
    await setup_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROXY_NAME: "Renamed", CONF_HIDE_SOURCE: False}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PROXY_NAME] == "Renamed"
    assert hass.states.get("switch.test_proxy").attributes["friendly_name"] == "Renamed"
