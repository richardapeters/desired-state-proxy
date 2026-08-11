"""Config flow for the Desired State Proxy integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_HIDE_SOURCE,
    CONF_PROXY_NAME,
    CONF_PROXY_TYPE,
    CONF_SOURCE_ENTITY,
    DOMAIN,
    PROXY_TYPE_AUTO,
    PROXY_TYPE_LIGHT,
    PROXY_TYPE_SWITCH,
    PROXY_TYPES,
)

SOURCE_DOMAINS = ["switch", "light"]


def _resolve_proxy_type(proxy_type: str, source_entity_id: str) -> str:
    """Resolve the effective proxy type for a source entity."""
    if proxy_type != PROXY_TYPE_AUTO:
        return proxy_type
    return PROXY_TYPE_LIGHT if source_entity_id.startswith("light.") else PROXY_TYPE_SWITCH


def _default_name(hass: Any, source_entity_id: str) -> str:
    """Return a sensible default name for the proxy."""
    state = hass.states.get(source_entity_id)
    if state is not None and (friendly := state.attributes.get("friendly_name")):
        return f"{friendly} Desired"
    return f"{source_entity_id.split('.', 1)[1].replace('_', ' ').title()} Desired"


class DesiredStateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Desired State Proxy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            source_entity_id: str = user_input[CONF_SOURCE_ENTITY]
            proxy_type: str = user_input.get(CONF_PROXY_TYPE, PROXY_TYPE_AUTO)
            source_domain = source_entity_id.split(".", 1)[0]

            if source_domain not in SOURCE_DOMAINS:
                errors[CONF_SOURCE_ENTITY] = "invalid_source_domain"
            elif self._is_proxy_entity(source_entity_id):
                errors[CONF_SOURCE_ENTITY] = "proxy_chain"
            elif self._is_already_proxied(source_entity_id):
                errors[CONF_SOURCE_ENTITY] = "already_proxied"
            elif proxy_type == PROXY_TYPE_SWITCH and source_domain != "switch":
                errors[CONF_PROXY_TYPE] = "invalid_proxy_type"

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{source_entity_id}")
                self._abort_if_unique_id_configured()

                name = (user_input.get(CONF_PROXY_NAME) or "").strip() or _default_name(
                    self.hass, source_entity_id
                )
                data = {
                    CONF_SOURCE_ENTITY: source_entity_id,
                    CONF_PROXY_TYPE: _resolve_proxy_type(proxy_type, source_entity_id),
                    CONF_PROXY_NAME: name,
                    CONF_HIDE_SOURCE: bool(user_input.get(CONF_HIDE_SOURCE, False)),
                }
                return self.async_create_entry(title=name, data=data, options={})

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(user_input),
            errors=errors,
        )

    @callback
    def _schema(self, user_input: dict[str, Any] | None) -> vol.Schema:
        """Build the user step schema, prefilled with previous input."""
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Required(
                    CONF_SOURCE_ENTITY,
                    description={"suggested_value": user_input.get(CONF_SOURCE_ENTITY)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SOURCE_DOMAINS)
                ),
                vol.Required(
                    CONF_PROXY_TYPE,
                    default=user_input.get(CONF_PROXY_TYPE, PROXY_TYPE_AUTO),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=PROXY_TYPES,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="proxy_type",
                    )
                ),
                vol.Optional(
                    CONF_PROXY_NAME,
                    description={"suggested_value": user_input.get(CONF_PROXY_NAME)},
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_HIDE_SOURCE,
                    default=user_input.get(CONF_HIDE_SOURCE, False),
                ): selector.BooleanSelector(),
            }
        )

    @callback
    def _is_already_proxied(self, entity_id: str) -> bool:
        """Return True when the entity is already the source of another proxy."""
        return any(
            entry.data.get(CONF_SOURCE_ENTITY) == entity_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        )

    @callback
    def _is_proxy_entity(self, entity_id: str) -> bool:
        """Return True when the entity is itself a proxy of this integration."""
        registry = er.async_get(self.hass)
        registry_entry = registry.async_get(entity_id)
        if registry_entry is not None and registry_entry.platform == DOMAIN:
            return True

        entry_ids = {entry.entry_id for entry in self.hass.config_entries.async_entries(DOMAIN)}
        return registry_entry is not None and registry_entry.config_entry_id in entry_ids

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DesiredStateOptionsFlow:
        """Return the options flow handler."""
        return DesiredStateOptionsFlow()


class DesiredStateOptionsFlow(OptionsFlow):
    """Handle options for a Desired State Proxy entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the proxy options."""
        entry = self.config_entry
        if user_input is not None:
            data = dict(entry.data)
            data[CONF_HIDE_SOURCE] = bool(user_input.get(CONF_HIDE_SOURCE, False))
            title = entry.title
            if name := (user_input.get(CONF_PROXY_NAME) or "").strip():
                data[CONF_PROXY_NAME] = name
                title = name
            self.hass.config_entries.async_update_entry(entry, data=data, title=title)
            return self.async_create_entry(title="", data=dict(entry.options))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PROXY_NAME,
                        description={
                            "suggested_value": entry.data.get(CONF_PROXY_NAME, entry.title)
                        },
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_HIDE_SOURCE,
                        default=bool(entry.data.get(CONF_HIDE_SOURCE, False)),
                    ): selector.BooleanSelector(),
                }
            ),
        )
