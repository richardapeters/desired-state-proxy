"""Constants for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "desired_state"

PLATFORM_SWITCH: Final = "switch"
PLATFORM_LIGHT: Final = "light"

# Configuration keys (stored in ConfigEntry.data)
CONF_SOURCE_ENTITY: Final = "source_entity"
CONF_PROXY_TYPE: Final = "proxy_type"
CONF_PROXY_NAME: Final = "proxy_name"
CONF_HIDE_SOURCE: Final = "hide_source"

# Proxy types
PROXY_TYPE_AUTO: Final = "auto"
PROXY_TYPE_SWITCH: Final = "switch"
PROXY_TYPE_LIGHT: Final = "light"

PROXY_TYPES: Final = [PROXY_TYPE_AUTO, PROXY_TYPE_SWITCH, PROXY_TYPE_LIGHT]

# Extra state attributes exposed by proxy entities
ATTR_SOURCE_ENTITY: Final = "source_entity"
ATTR_DESIRED_STATE: Final = "desired_state"
ATTR_ACTUAL_STATE: Final = "actual_state"
ATTR_PENDING: Final = "pending"
ATTR_DESIRED_BRIGHTNESS: Final = "desired_brightness"
ATTR_DESIRED_COLOR_TEMP: Final = "desired_color_temp"
ATTR_DESIRED_RGB_COLOR: Final = "desired_rgb_color"

# Option keys used to persist the desired state in ConfigEntry.options
OPT_DESIRED_ON: Final = "desired_on"
OPT_DESIRED_BRIGHTNESS: Final = "desired_brightness"
OPT_DESIRED_COLOR_TEMP: Final = "desired_color_temp"
OPT_DESIRED_RGB_COLOR: Final = "desired_rgb_color"
OPT_DESIRED_HS_COLOR: Final = "desired_hs_color"
OPT_HIDDEN_SOURCE: Final = "hidden_source"

# Reconciliation behaviour
RECONCILE_RETRY_DELAY: Final = 5.0
RECONCILE_MAX_ATTEMPTS: Final = 3
