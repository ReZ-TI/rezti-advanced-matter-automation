"""Config flow for Matter Knob Proxy integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
)

from .const import (
    DOMAIN,
    CONF_DIMMER_TARGET,
    CONF_CW_TARGET,
    CONF_CURTAIN1_TARGET,
    CONF_CURTAIN2_TARGET,
    CONF_SOURCE_DIMMER,
    CONF_SOURCE_CW,
    CONF_SOURCE_CURTAIN1,
    CONF_SOURCE_CURTAIN2,
)

_LOGGER = logging.getLogger(__name__)


class MatterKnobProxyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Matter Knob Proxy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step to select source and target entities."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate that at least one source-target pair is configured
            has_source = any([
                user_input.get(CONF_SOURCE_DIMMER),
                user_input.get(CONF_SOURCE_CW),
                user_input.get(CONF_SOURCE_CURTAIN1),
                user_input.get(CONF_SOURCE_CURTAIN2),
            ])
            
            has_target = any([
                user_input.get(CONF_DIMMER_TARGET),
                user_input.get(CONF_CW_TARGET),
                user_input.get(CONF_CURTAIN1_TARGET),
                user_input.get(CONF_CURTAIN2_TARGET),
            ])

            if not has_source:
                errors["base"] = "missing_source"
            elif not has_target:
                errors["base"] = "missing_target"
            else:
                # Build source and target mappings
                source_entities = {
                    1: user_input.get(CONF_SOURCE_DIMMER),
                    2: user_input.get(CONF_SOURCE_CW),
                    3: user_input.get(CONF_SOURCE_CURTAIN1),
                    4: user_input.get(CONF_SOURCE_CURTAIN2),
                }
                target_entities = {
                    1: user_input.get(CONF_DIMMER_TARGET),
                    2: user_input.get(CONF_CW_TARGET),
                    3: user_input.get(CONF_CURTAIN1_TARGET),
                    4: user_input.get(CONF_CURTAIN2_TARGET),
                }
                
                # Generate unique ID from first configured source
                unique_id = None
                for entity_id in source_entities.values():
                    if entity_id:
                        unique_id = entity_id
                        break
                
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Create the config entry
                return self.async_create_entry(
                    title=f"Knob Proxy ({unique_id})",
                    data={
                        "source_entities": source_entities,
                        "target_entities": target_entities,
                    },
                )

        # Build the entity selector schema with sections
        data_schema = vol.Schema({
            # Source entities (the "knob" inputs)
            vol.Optional(CONF_SOURCE_DIMMER): EntitySelector(
                EntitySelectorConfig(domain=[LIGHT_DOMAIN,NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_SOURCE_CW): EntitySelector(
                EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_SOURCE_CURTAIN1): EntitySelector(
                EntitySelectorConfig(domain=[COVER_DOMAIN,NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_SOURCE_CURTAIN2): EntitySelector(
                EntitySelectorConfig(domain=[COVER_DOMAIN,NUMBER_DOMAIN])
            ),
            # Target entities (what to control)
            vol.Optional(CONF_DIMMER_TARGET): EntitySelector(
                EntitySelectorConfig(domain=[LIGHT_DOMAIN,NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_CW_TARGET): EntitySelector(
                EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_CURTAIN1_TARGET): EntitySelector(
                EntitySelectorConfig(domain=[COVER_DOMAIN,NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_CURTAIN2_TARGET): EntitySelector(
                EntitySelectorConfig(domain=[COVER_DOMAIN,NUMBER_DOMAIN])
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "source_section": "Source Entities (Your Knob Inputs)",
                "target_section": "Target Entities (What to Control)",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MatterKnobProxyOptionsFlow:
        """Create the options flow."""
        return MatterKnobProxyOptionsFlow(config_entry)


class MatterKnobProxyOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for updating entity mappings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        pass

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Build updated source and target mappings
            source_entities = {
                1: user_input.get(CONF_SOURCE_DIMMER),
                2: user_input.get(CONF_SOURCE_CW),
                3: user_input.get(CONF_SOURCE_CURTAIN1),
                4: user_input.get(CONF_SOURCE_CURTAIN2),
            }
            target_entities = {
                1: user_input.get(CONF_DIMMER_TARGET),
                2: user_input.get(CONF_CW_TARGET),
                3: user_input.get(CONF_CURTAIN1_TARGET),
                4: user_input.get(CONF_CURTAIN2_TARGET),
            }
            
            # Update the config entry data
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    "source_entities": source_entities,
                    "target_entities": target_entities,
                },
            )
            return self.async_create_entry(title="", data={})

        # Pre-fill current values from entry data
        current_data = self.config_entry.data
        source_entities = current_data.get("source_entities", {})
        target_entities = current_data.get("target_entities", {})

        data_schema = vol.Schema({
            # Source entities
            vol.Optional(
                CONF_SOURCE_DIMMER,
                default=source_entities.get(1)
            ): EntitySelector(EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_SOURCE_CW,
                default=source_entities.get(2)
            ): EntitySelector(EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_SOURCE_CURTAIN1,
                default=source_entities.get(3)
            ): EntitySelector(EntitySelectorConfig(domain=[COVER_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_SOURCE_CURTAIN2,
                default=source_entities.get(4)
            ): EntitySelector(EntitySelectorConfig(domain=[COVER_DOMAIN, NUMBER_DOMAIN])),
            # Target entities  
            vol.Optional(
                CONF_DIMMER_TARGET,
                default=target_entities.get(1)
            ): EntitySelector(EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_CW_TARGET,
                default=target_entities.get(2)
            ): EntitySelector(EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_CURTAIN1_TARGET,
                default=target_entities.get(3)
            ): EntitySelector(EntitySelectorConfig(domain=[COVER_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_CURTAIN2_TARGET,
                default=target_entities.get(4)
            ): EntitySelector(EntitySelectorConfig(domain=[COVER_DOMAIN, NUMBER_DOMAIN])),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
