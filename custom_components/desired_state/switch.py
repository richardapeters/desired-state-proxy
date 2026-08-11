"""Switch platform for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ProxyCoordinator
from .entity import ProxyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the proxy switch from a config entry."""
    coordinator: ProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ProxySwitch(coordinator, entry)])


class ProxySwitch(ProxyEntity, SwitchEntity):
    """A switch entity representing the desired state of a source switch."""

    @property
    def is_on(self) -> bool:
        """Return the desired state, never the actual state of the source."""
        return self.coordinator.desired_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the desired state to on and reconcile the source."""
        await self.coordinator.async_set_desired(on=True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the desired state to off and reconcile the source."""
        await self.coordinator.async_set_desired(on=False)
        self.async_write_ha_state()
