"""Coordinator holding and reconciling the desired state of a proxied entity."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    CONF_SOURCE_ENTITY,
    OPT_DESIRED_BRIGHTNESS,
    OPT_DESIRED_COLOR_TEMP,
    OPT_DESIRED_HS_COLOR,
    OPT_DESIRED_ON,
    OPT_DESIRED_RGB_COLOR,
    RECONCILE_MAX_ATTEMPTS,
    RECONCILE_RETRY_DELAY,
)

_LOGGER = logging.getLogger(__name__)

ATTR_BRIGHTNESS = "brightness"
ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
ATTR_RGB_COLOR = "rgb_color"
ATTR_HS_COLOR = "hs_color"


def _as_int(value: Any) -> int | None:
    """Return value as int, or None when it cannot be converted."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_int_tuple(value: Any) -> tuple[int, ...] | None:
    """Return value as a tuple of ints, or None when it cannot be converted."""
    if value is None:
        return None
    try:
        return tuple(int(item) for item in value)
    except (TypeError, ValueError):
        return None


def _as_float_tuple(value: Any) -> tuple[float, ...] | None:
    """Return value as a tuple of floats, or None when it cannot be converted."""
    if value is None:
        return None
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None


class ProxyCoordinator:
    """Event driven coordinator that keeps a source entity in the desired state.

    This is deliberately *not* a DataUpdateCoordinator: there is nothing to poll.
    The coordinator listens for state changes of the source entity and pushes the
    desired state towards it whenever the source is available and out of sync.
    """

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        self.source_entity_id: str = entry.data[CONF_SOURCE_ENTITY]

        options = dict(entry.options)
        self.desired_on: bool = bool(options.get(OPT_DESIRED_ON, False))
        self.desired_brightness: int | None = _as_int(options.get(OPT_DESIRED_BRIGHTNESS))
        self.desired_color_temp: int | None = _as_int(options.get(OPT_DESIRED_COLOR_TEMP))
        self.desired_rgb_color: tuple[int, ...] | None = _as_int_tuple(
            options.get(OPT_DESIRED_RGB_COLOR)
        )
        self.desired_hs_color: tuple[float, ...] | None = _as_float_tuple(
            options.get(OPT_DESIRED_HS_COLOR)
        )

        self.setup_signature: tuple[object, ...] | None = None
        self._listeners: list[Any] = []
        self._unsub_state: Any = None
        self._unsub_retry: Any = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._reconcile_attempts = 0
        self._reconciling = False
        self._shutdown = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Start listening to the source entity."""
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.source_entity_id], self._handle_source_state_event
        )

    async def async_shutdown(self) -> None:
        """Cancel all listeners and pending tasks."""
        self._shutdown = True
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        self._cancel_retry()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        self._tasks.clear()
        self._listeners.clear()

    # ------------------------------------------------------------------
    # Entity notification plumbing
    # ------------------------------------------------------------------
    @callback
    def async_add_listener(self, update_callback: Any) -> Any:
        """Register an update callback, returns an unsubscribe callable."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def async_update_listeners(self) -> None:
        """Inform all registered entities that the state changed."""
        for update_callback in list(self._listeners):
            update_callback()

    # ------------------------------------------------------------------
    # Source state helpers
    # ------------------------------------------------------------------
    @property
    def source_domain(self) -> str:
        """Return the domain of the source entity."""
        return self.source_entity_id.split(".", 1)[0]

    @property
    def source_state(self) -> State | None:
        """Return the current state object of the source entity."""
        return self.hass.states.get(self.source_entity_id)

    @property
    def source_available(self) -> bool:
        """Return whether the source entity currently reports a usable state."""
        state = self.source_state
        return state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)

    @property
    def actual_state(self) -> str | None:
        """Return the raw state string of the source entity."""
        state = self.source_state
        return state.state if state is not None else None

    @property
    def actual_on(self) -> bool | None:
        """Return whether the source entity is on, None when unknown."""
        state = self.source_state
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        return state.state == STATE_ON

    @property
    def pending(self) -> bool:
        """Return True when the source does not (yet) match the desired state."""
        if not self.source_available:
            return True
        return not self._attributes_in_sync()

    # ------------------------------------------------------------------
    # Desired state mutation
    # ------------------------------------------------------------------
    async def async_set_desired(
        self,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        color_temp: int | None = None,
        rgb_color: Any = None,
        hs_color: Any = None,
        reconcile: bool = True,
    ) -> None:
        """Update the desired state, persist it and reconcile the source."""
        if on is not None:
            self.desired_on = bool(on)
        if brightness is not None:
            self.desired_brightness = _as_int(brightness)
        if color_temp is not None:
            self.desired_color_temp = _as_int(color_temp)
        if rgb_color is not None:
            self.desired_rgb_color = _as_int_tuple(rgb_color)
            self.desired_hs_color = None
        if hs_color is not None:
            self.desired_hs_color = _as_float_tuple(hs_color)

        self._async_persist()
        self.async_update_listeners()

        if reconcile:
            self._reconcile_attempts = 0
            await self.async_reconcile()

    @callback
    def _async_persist(self) -> None:
        """Persist the desired state into the config entry options."""
        options = dict(self.entry.options)
        options[OPT_DESIRED_ON] = self.desired_on
        options[OPT_DESIRED_BRIGHTNESS] = self.desired_brightness
        options[OPT_DESIRED_COLOR_TEMP] = self.desired_color_temp
        options[OPT_DESIRED_RGB_COLOR] = (
            list(self.desired_rgb_color) if self.desired_rgb_color is not None else None
        )
        options[OPT_DESIRED_HS_COLOR] = (
            list(self.desired_hs_color) if self.desired_hs_color is not None else None
        )
        if options != dict(self.entry.options):
            self.hass.config_entries.async_update_entry(self.entry, options=options)

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    @callback
    def _handle_source_state_event(self, event: Event[EventStateChangedData]) -> None:
        """Handle a state change of the source entity."""
        self.async_update_listeners()
        if self._shutdown:
            return

        old_state = event.data.get("old_state")
        was_unavailable = old_state is None or old_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )
        if was_unavailable and self.source_available:
            # The source just came back; give reconciliation a fresh set of attempts.
            self._reconcile_attempts = 0

        self._async_schedule_reconcile()

    @callback
    def _async_schedule_reconcile(self) -> None:
        """Schedule a reconciliation run as a tracked task."""
        if self._shutdown:
            return
        task = self.hass.async_create_task(self.async_reconcile())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @callback
    def _cancel_retry(self) -> None:
        """Cancel a pending retry timer."""
        if self._unsub_retry is not None:
            self._unsub_retry()
            self._unsub_retry = None

    def _attributes_in_sync(self) -> bool:
        """Return whether the source matches the desired state (incl. attributes)."""
        actual_on = self.actual_on
        if actual_on is None or actual_on is not self.desired_on:
            return False
        if not self.desired_on:
            return True
        if self.source_domain != "light":
            return True

        state = self.source_state
        assert state is not None
        if (
            self.desired_brightness is not None
            and _as_int(state.attributes.get(ATTR_BRIGHTNESS)) != self.desired_brightness
        ):
            return False
        if self.desired_rgb_color is not None:
            return _as_int_tuple(state.attributes.get(ATTR_RGB_COLOR)) == self.desired_rgb_color
        if self.desired_color_temp is not None:
            return (
                _as_int(state.attributes.get(ATTR_COLOR_TEMP_KELVIN))
                == self.desired_color_temp
            )
        return True

    def _build_turn_on_data(self) -> dict[str, Any]:
        """Build the service data for a turn_on call."""
        data: dict[str, Any] = {ATTR_ENTITY_ID: self.source_entity_id}
        if self.source_domain != "light":
            return data
        if self.desired_brightness is not None:
            data[ATTR_BRIGHTNESS] = self.desired_brightness
        if self.desired_rgb_color is not None:
            data[ATTR_RGB_COLOR] = list(self.desired_rgb_color)
        elif self.desired_color_temp is not None:
            data[ATTR_COLOR_TEMP_KELVIN] = self.desired_color_temp
        return data

    async def async_reconcile(self, *, force: bool = False) -> bool:
        """Push the desired state to the source entity when needed.

        Returns True when a service call was made.
        """
        if self._shutdown:
            return False
        if self._reconciling:
            return False
        if not self.source_available:
            _LOGGER.debug(
                "Source %s unavailable, deferring reconciliation", self.source_entity_id
            )
            return False
        if not force and self._attributes_in_sync():
            self._cancel_retry()
            self._reconcile_attempts = 0
            return False
        if not force and self._reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
            _LOGGER.debug(
                "Not reconciling %s again, %s attempts did not bring it in sync",
                self.source_entity_id,
                self._reconcile_attempts,
            )
            return False

        self._reconciling = True
        try:
            domain = self.source_domain
            if self.desired_on:
                service = SERVICE_TURN_ON
                data = self._build_turn_on_data()
            else:
                service = SERVICE_TURN_OFF
                data = {ATTR_ENTITY_ID: self.source_entity_id}

            if not self.hass.services.has_service(domain, service):
                _LOGGER.debug(
                    "Service %s.%s not available yet, deferring reconciliation of %s",
                    domain,
                    service,
                    self.source_entity_id,
                )
                return False

            _LOGGER.debug("Reconciling %s: %s.%s %s", self.source_entity_id, domain, service, data)
            self._reconcile_attempts += 1
            try:
                await self.hass.services.async_call(domain, service, data, blocking=True)
            except Exception:  # never let a failing device break the proxy
                _LOGGER.exception(
                    "Error calling %s.%s for %s", domain, service, self.source_entity_id
                )
        finally:
            self._reconciling = False

        self.async_update_listeners()
        self._async_schedule_retry_if_needed()
        return True

    @callback
    def _async_schedule_retry_if_needed(self) -> None:
        """Schedule another reconciliation attempt when still out of sync."""
        if self._shutdown:
            return
        if self._attributes_in_sync():
            self._cancel_retry()
            self._reconcile_attempts = 0
            return
        if self._reconcile_attempts >= RECONCILE_MAX_ATTEMPTS:
            _LOGGER.warning(
                "Giving up reconciling %s after %s attempts; the desired state is kept "
                "and will be applied again when the source changes",
                self.source_entity_id,
                self._reconcile_attempts,
            )
            return

        self._cancel_retry()

        @callback
        def _retry(_now: Any) -> None:
            self._unsub_retry = None
            self._async_schedule_reconcile()

        self._unsub_retry = async_call_later(self.hass, RECONCILE_RETRY_DELAY, _retry)

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------
    def as_diagnostics(self) -> dict[str, Any]:
        """Return a serializable snapshot of the coordinator state."""
        state = self.source_state
        return {
            "source_entity_id": self.source_entity_id,
            "source_domain": self.source_domain,
            "source_available": self.source_available,
            "actual_state": self.actual_state,
            "actual_attributes": dict(state.attributes) if state is not None else None,
            "desired_on": self.desired_on,
            "desired_state": STATE_ON if self.desired_on else STATE_OFF,
            "desired_brightness": self.desired_brightness,
            "desired_color_temp": self.desired_color_temp,
            "desired_rgb_color": (
                list(self.desired_rgb_color) if self.desired_rgb_color is not None else None
            ),
            "desired_hs_color": (
                list(self.desired_hs_color) if self.desired_hs_color is not None else None
            ),
            "in_sync": self.source_available and self._attributes_in_sync(),
            "pending": self.pending,
            "reconcile_attempts": self._reconcile_attempts,
        }
