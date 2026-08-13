"""Diagnostics support for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
)
from .coordinator import ProxyCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: ProxyCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    registry = er.async_get(hass)
    proxy_entries = [
        registry_entry
        for registry_entry in registry.entities.values()
        if registry_entry.config_entry_id == entry.entry_id
    ]

    source_entity_id: str = entry.data.get(CONF_SOURCE_ENTITY, "")
    source_registry_entry = registry.async_get(source_entity_id) if source_entity_id else None
    source_state = hass.states.get(source_entity_id) if source_entity_id else None

    diagnostics: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "proxy": {
            "name": entry.data.get(CONF_PROXY_NAME),
            "type": entry.data.get(CONF_PROXY_TYPE),
            "hide_source": entry.data.get(CONF_HIDE_SOURCE, False),
            "entities": [
                {
                    "entity_id": registry_entry.entity_id,
                    "platform": registry_entry.platform,
                    "state": (
                        state.state
                        if (state := hass.states.get(registry_entry.entity_id)) is not None
                        else None
                    ),
                }
                for registry_entry in proxy_entries
            ],
        },
        "source": {
            "entity_id": source_entity_id,
            "state": source_state.state if source_state is not None else None,
            "attributes": dict(source_state.attributes) if source_state is not None else None,
            "hidden_by": (
                str(source_registry_entry.hidden_by)
                if source_registry_entry is not None and source_registry_entry.hidden_by
                else None
            ),
            "available": source_state is not None
            and source_state.state not in ("unavailable", "unknown"),
        },
    }

    if coordinator is not None:
        diagnostics["coordinator"] = coordinator.as_diagnostics()
        diagnostics["sync"] = {
            "in_sync": coordinator.source_available and not coordinator.pending,
            "pending": coordinator.pending,
        }
    else:
        diagnostics["coordinator"] = None
        diagnostics["sync"] = {"in_sync": False, "pending": True}

    return diagnostics
