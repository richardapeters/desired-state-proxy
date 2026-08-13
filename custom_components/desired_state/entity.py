"""Base entity for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_ACTUAL_STATE,
    ATTR_DESIRED_BRIGHTNESS,
    ATTR_DESIRED_COLOR_TEMP,
    ATTR_DESIRED_RGB_COLOR,
    ATTR_DESIRED_STATE,
    ATTR_PENDING,
    ATTR_SOURCE_ENTITY,
    CONF_PROXY_NAME,
    DOMAIN,
    OPT_DESIRED_ON,
)
from .coordinator import ProxyCoordinator


class ProxyEntity(RestoreEntity):
    """Base class for proxy entities representing a desired state."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, coordinator: ProxyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the proxy entity."""
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data.get(CONF_PROXY_NAME) or entry.title
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=self._attr_name,
            manufacturer="Desired State Proxy",
            entry_type=None,
        )

    @property
    def coordinator(self) -> ProxyCoordinator:
        """Return the coordinator backing this entity."""
        return self._coordinator

    @property
    def source_entity_id(self) -> str:
        """Return the entity id of the proxied source entity."""
        return self._coordinator.source_entity_id

    @property
    def available(self) -> bool:
        """A proxy is always available, even when the source is not."""
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the proxy specific attributes."""
        coordinator = self._coordinator
        attributes: dict[str, Any] = {
            ATTR_SOURCE_ENTITY: coordinator.source_entity_id,
            ATTR_DESIRED_STATE: STATE_ON if coordinator.desired_on else STATE_OFF,
            ATTR_ACTUAL_STATE: coordinator.actual_state,
            ATTR_PENDING: coordinator.pending,
        }
        if coordinator.desired_brightness is not None:
            attributes[ATTR_DESIRED_BRIGHTNESS] = coordinator.desired_brightness
        if coordinator.desired_color_temp is not None:
            attributes[ATTR_DESIRED_COLOR_TEMP] = coordinator.desired_color_temp
        if coordinator.desired_rgb_color is not None:
            attributes[ATTR_DESIRED_RGB_COLOR] = list(coordinator.desired_rgb_color)
        return attributes

    async def async_added_to_hass(self) -> None:
        """Register callbacks and restore the last known desired state."""
        await super().async_added_to_hass()

        if (
            OPT_DESIRED_ON not in self._entry.options
            and (last_state := await self.async_get_last_state()) is not None
        ):
            await self._async_restore_desired_state(last_state)

        self.async_on_remove(self._coordinator.async_add_listener(self._handle_update))

    async def _async_restore_desired_state(self, last_state: State) -> None:
        """Restore the desired state from the last known entity state.

        The config entry options are authoritative; this is only used when no
        desired state has been persisted yet, for example right after an upgrade.
        """
        if last_state.state not in (STATE_ON, STATE_OFF):
            return
        await self._coordinator.async_set_desired(on=last_state.state == STATE_ON)

    @callback
    def _handle_update(self) -> None:
        """Handle an update from the coordinator."""
        self.async_write_ha_state()
