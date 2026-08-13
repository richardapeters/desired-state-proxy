"""Light platform for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_SUPPORTED_FEATURES, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import color as color_util

from .const import DOMAIN
from .coordinator import ProxyCoordinator
from .entity import ProxyEntity

DEFAULT_MIN_COLOR_TEMP_KELVIN = 2000
DEFAULT_MAX_COLOR_TEMP_KELVIN = 6535


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the proxy light from a config entry."""
    coordinator: ProxyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ProxyLight(coordinator, entry)])


class ProxyLight(ProxyEntity, LightEntity):
    """A light entity representing the desired state of a source light or switch."""

    def __init__(self, coordinator: ProxyCoordinator, entry: ConfigEntry) -> None:
        """Initialize the proxy light."""
        super().__init__(coordinator, entry)
        self._cached_color_modes: set[ColorMode] | None = None
        self._cached_features: LightEntityFeature | None = None
        self._cached_min_kelvin: int | None = None
        self._cached_max_kelvin: int | None = None
        self._refresh_source_capabilities()

    # ------------------------------------------------------------------
    # Capability discovery
    # ------------------------------------------------------------------
    @property
    def _source_is_light(self) -> bool:
        """Return whether the proxied source entity is a light."""
        return self.coordinator.source_domain == "light"

    def _refresh_source_capabilities(self) -> None:
        """Cache the capabilities of the source light while it is available."""
        if not self._source_is_light:
            return
        state = self.coordinator.source_state
        if state is None:
            return

        modes = state.attributes.get(ATTR_SUPPORTED_COLOR_MODES)
        if modes:
            parsed: set[ColorMode] = set()
            for mode in modes:
                try:
                    parsed.add(ColorMode(mode))
                except ValueError:
                    continue
            if parsed:
                self._cached_color_modes = parsed

        features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
        if features is not None:
            try:
                self._cached_features = LightEntityFeature(int(features))
            except (TypeError, ValueError):
                self._cached_features = None

        if (min_kelvin := state.attributes.get("min_color_temp_kelvin")) is not None:
            try:
                self._cached_min_kelvin = int(min_kelvin)
            except (TypeError, ValueError):
                pass
        if (max_kelvin := state.attributes.get("max_color_temp_kelvin")) is not None:
            try:
                self._cached_max_kelvin = int(max_kelvin)
            except (TypeError, ValueError):
                pass

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the color modes supported by the source entity."""
        if not self._source_is_light:
            return {ColorMode.ONOFF}
        self._refresh_source_capabilities()
        if self._cached_color_modes:
            return self._cached_color_modes
        return {ColorMode.ONOFF}

    @property
    def supported_features(self) -> LightEntityFeature:
        """Return the features supported by the source entity."""
        if not self._source_is_light:
            return LightEntityFeature(0)
        self._refresh_source_capabilities()
        if self._cached_features is not None:
            return self._cached_features
        return LightEntityFeature(0)

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the coldest color temperature the source supports."""
        if self._cached_min_kelvin is not None:
            return self._cached_min_kelvin
        return DEFAULT_MIN_COLOR_TEMP_KELVIN

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the warmest color temperature the source supports."""
        if self._cached_max_kelvin is not None:
            return self._cached_max_kelvin
        return DEFAULT_MAX_COLOR_TEMP_KELVIN

    # ------------------------------------------------------------------
    # Desired state properties
    # ------------------------------------------------------------------
    @property
    def is_on(self) -> bool:
        """Return the desired state, never the actual state of the source."""
        return self.coordinator.desired_on

    @property
    def brightness(self) -> int | None:
        """Return the desired brightness."""
        modes = self.supported_color_modes
        if modes == {ColorMode.ONOFF}:
            return None
        return self.coordinator.desired_brightness

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the desired color temperature in Kelvin."""
        if ColorMode.COLOR_TEMP not in self.supported_color_modes:
            return None
        return self.coordinator.desired_color_temp

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the desired RGB color."""
        rgb = self.coordinator.desired_rgb_color
        if rgb is None or len(rgb) < 3:
            return None
        return (rgb[0], rgb[1], rgb[2])

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the desired HS color."""
        if (rgb := self.rgb_color) is not None:
            return color_util.color_RGB_to_hs(*rgb)
        hs = self.coordinator.desired_hs_color
        if hs is None or len(hs) < 2:
            return None
        return (hs[0], hs[1])

    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode matching the desired state."""
        modes = self.supported_color_modes
        if modes == {ColorMode.ONOFF}:
            return ColorMode.ONOFF
        if self.coordinator.desired_rgb_color is not None and ColorMode.RGB in modes:
            return ColorMode.RGB
        if self.coordinator.desired_rgb_color is not None and ColorMode.HS in modes:
            return ColorMode.HS
        if self.coordinator.desired_color_temp is not None and ColorMode.COLOR_TEMP in modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in modes:
            return ColorMode.BRIGHTNESS
        for mode in (ColorMode.RGB, ColorMode.HS, ColorMode.COLOR_TEMP):
            if mode in modes:
                return mode
        return next(iter(modes))

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Update the desired state to on and remember the light parameters."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        hs_color = kwargs.get(ATTR_HS_COLOR)

        if rgb_color is None and hs_color is not None:
            rgb_color = color_util.color_hs_to_RGB(*hs_color)

        if not self._source_is_light:
            brightness = color_temp = rgb_color = hs_color = None

        await self.coordinator.async_set_desired(
            on=True,
            brightness=brightness,
            color_temp=color_temp,
            rgb_color=rgb_color,
            hs_color=hs_color,
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Update the desired state to off."""
        await self.coordinator.async_set_desired(on=False)
        self.async_write_ha_state()

    async def _async_restore_desired_state(self, last_state: State) -> None:
        """Restore the desired light parameters from the last known state."""
        if last_state.state not in (STATE_ON, STATE_OFF):
            return
        await self.coordinator.async_set_desired(
            on=last_state.state == STATE_ON,
            brightness=last_state.attributes.get(ATTR_BRIGHTNESS),
            color_temp=last_state.attributes.get(ATTR_COLOR_TEMP_KELVIN),
            rgb_color=last_state.attributes.get(ATTR_RGB_COLOR),
        )
