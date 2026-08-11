"""The Desired State Proxy integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    OPT_HIDDEN_SOURCE,
    PROXY_TYPE_LIGHT,
    PROXY_TYPE_SWITCH,
)
from .coordinator import ProxyCoordinator

_LOGGER = logging.getLogger(__name__)


def _setup_signature(entry: ConfigEntry) -> tuple[object, ...]:
    """Return the parts of the configuration that require a reload when changed."""
    return (
        entry.title,
        entry.data.get(CONF_SOURCE_ENTITY),
        entry.data.get(CONF_PROXY_TYPE),
        entry.data.get(CONF_PROXY_NAME),
        bool(entry.data.get(CONF_HIDE_SOURCE)),
    )


def _platform_for_entry(entry: ConfigEntry) -> Platform:
    """Return the platform that should be set up for this entry."""
    if entry.data.get(CONF_PROXY_TYPE) == PROXY_TYPE_LIGHT:
        return Platform.LIGHT
    if entry.data.get(CONF_PROXY_TYPE) == PROXY_TYPE_SWITCH:
        return Platform.SWITCH
    source: str = entry.data[CONF_SOURCE_ENTITY]
    return Platform.LIGHT if source.startswith("light.") else Platform.SWITCH


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Desired State Proxy from a config entry."""
    coordinator = ProxyCoordinator(hass, entry)
    coordinator.setup_signature = _setup_signature(entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_setup()

    if entry.data.get(CONF_HIDE_SOURCE):
        await _async_hide_source(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, [_platform_for_entry(entry)])

    await coordinator.async_reconcile()

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its configuration (not its desired state) changed."""
    coordinator: ProxyCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return
    if coordinator.setup_signature != _setup_signature(entry):
        hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [_platform_for_entry(entry)]
    )

    coordinator: ProxyCoordinator | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if coordinator is not None:
        await coordinator.async_shutdown()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)

    await _async_restore_source_visibility(hass, entry)

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry."""
    await _async_restore_source_visibility(hass, entry)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)


async def _async_hide_source(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Hide the source entity so only the proxy is shown to the user."""
    registry = er.async_get(hass)
    source_entity_id: str = entry.data[CONF_SOURCE_ENTITY]
    source_entry = registry.async_get(source_entity_id)
    if source_entry is None:
        _LOGGER.debug("Source entity %s is not in the registry", source_entity_id)
        return
    if source_entry.hidden_by is not None:
        return

    registry.async_update_entity(
        source_entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
    )
    options = dict(entry.options)
    options[OPT_HIDDEN_SOURCE] = True
    hass.config_entries.async_update_entry(entry, options=options)


async def _async_restore_source_visibility(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unhide the source entity when this integration hid it."""
    if not entry.options.get(OPT_HIDDEN_SOURCE):
        return

    registry = er.async_get(hass)
    source_entity_id: str = entry.data[CONF_SOURCE_ENTITY]
    source_entry = registry.async_get(source_entity_id)
    if source_entry is not None and source_entry.hidden_by == er.RegistryEntryHider.INTEGRATION:
        registry.async_update_entity(source_entity_id, hidden_by=None)

    options = dict(entry.options)
    options.pop(OPT_HIDDEN_SOURCE, None)
    hass.config_entries.async_update_entry(entry, options=options)
