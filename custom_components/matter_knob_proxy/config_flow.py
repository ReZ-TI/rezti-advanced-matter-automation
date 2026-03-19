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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    DEFAULT_VID,
    DEFAULT_PID,
    CONF_KNOB_DEVICE_ID,
    CONF_DIMMER_TARGET,
    CONF_CW_TARGET,
    CONF_CURTAIN1_TARGET,
    CONF_CURTAIN2_TARGET,
)

_LOGGER = logging.getLogger(__name__)


class MatterKnobProxyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Matter Knob Proxy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._knob_device_id: str | None = None
        self._knob_node_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step to select a knob device."""
        errors: dict[str, str] = {}

        # Check if Matter integration is loaded
        if "matter" not in self.hass.config.components:
            return self.async_abort(reason="matter_not_loaded")

        # Discover available Matter knobs
        available_knobs = await self._discover_knobs()

        if not available_knobs:
            return self.async_abort(reason="no_knobs_found")

        if user_input is not None:
            device_id = user_input[CONF_KNOB_DEVICE_ID]
            
            # Check if this knob is already configured
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            # Store device info and proceed to entity mapping
            self._knob_device_id = device_id
            knob_info = available_knobs[device_id]
            self._knob_node_id = knob_info.get("node_id")

            return await self.async_step_entities()

        # Build selector options
        knob_options = [
            {"value": device_id, "label": info["name"]} 
            for device_id, info in available_knobs.items()
        ]

        data_schema = vol.Schema({
            vol.Required(CONF_KNOB_DEVICE_ID): SelectSelector(
                SelectSelectorConfig(
                    options=knob_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the entity mapping step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate that at least one mapping is configured
            has_mapping = any([
                user_input.get(CONF_DIMMER_TARGET),
                user_input.get(CONF_CW_TARGET),
                user_input.get(CONF_CURTAIN1_TARGET),
                user_input.get(CONF_CURTAIN2_TARGET),
            ])

            if not has_mapping:
                errors["base"] = "missing_mappings"
            else:
                # Create the config entry
                return self.async_create_entry(
                    title=f"Matter Knob Proxy ({self._knob_device_id})",
                    data={
                        CONF_KNOB_DEVICE_ID: self._knob_device_id,
                        "node_id": self._knob_node_id,
                    },
                    options=user_input,
                )

        # Build the entity selector schema
        data_schema = vol.Schema({
            vol.Optional(CONF_DIMMER_TARGET): EntitySelector(
                EntitySelectorConfig(domain=LIGHT_DOMAIN)
            ),
            vol.Optional(CONF_CW_TARGET): EntitySelector(
                EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])
            ),
            vol.Optional(CONF_CURTAIN1_TARGET): EntitySelector(
                EntitySelectorConfig(domain=COVER_DOMAIN)
            ),
            vol.Optional(CONF_CURTAIN2_TARGET): EntitySelector(
                EntitySelectorConfig(domain=COVER_DOMAIN)
            ),
        })

        return self.async_show_form(
            step_id="entities",
            data_schema=data_schema,
            errors=errors,
        )

    async def _discover_knobs(self) -> dict[str, dict[str, Any]]:
        """Discover available Matter knob devices.
        
        Scans the device registry for Matter devices matching the knob's VID/PID.
        Excludes devices that are already configured.
        
        Returns:
            Dictionary mapping device_id to device info.
        """
        device_registry = dr.async_get(self.hass)
        available_knobs = {}

        # Get existing config entries to exclude already configured knobs
        existing_devices = {
            entry.data.get(CONF_KNOB_DEVICE_ID) 
            for entry in self._async_current_entries()
        }

        for device in device_registry.devices.values():
            # Check if this is a Matter device
            if not any(
                identifier[0] == "matter" for identifier in device.identifiers
            ):
                continue

            # Skip already configured devices
            if device.id in existing_devices:
                continue

            # Check manufacturer data for VID/PID match
            # Matter devices store this in manufacturer/model or via matter integration data
            manufacturer = device.manufacturer or ""
            model = device.model or ""

            # Match by VID/PID in manufacturer/model fields
            # Format varies by Matter integration version, so we check multiple patterns
            vid_match = DEFAULT_VID.lower() in manufacturer.lower() or \
                       DEFAULT_VID.lower() in model.lower()
            pid_match = DEFAULT_PID.lower() in manufacturer.lower() or \
                       DEFAULT_PID.lower() in model.lower()

            # Also accept if device name contains "knob" (fallback for custom firmware)
            name_match = "knob" in device.name.lower()

            if (vid_match and pid_match) or name_match:
                # Extract node_id from device identifiers
                node_id = None
                for domain, value in device.identifiers:
                    if domain == "matter":
                        node_id = value
                        break

                available_knobs[device.id] = {
                    "name": device.name or f"Matter Device {device.id[:8]}",
                    "node_id": node_id,
                    "manufacturer": manufacturer,
                    "model": model,
                }

        return available_knobs

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
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Pre-fill current values
        current_options = self.config_entry.options

        data_schema = vol.Schema({
            vol.Optional(
                CONF_DIMMER_TARGET,
                default=current_options.get(CONF_DIMMER_TARGET)
            ): EntitySelector(EntitySelectorConfig(domain=LIGHT_DOMAIN)),
            vol.Optional(
                CONF_CW_TARGET,
                default=current_options.get(CONF_CW_TARGET)
            ): EntitySelector(EntitySelectorConfig(domain=[LIGHT_DOMAIN, NUMBER_DOMAIN])),
            vol.Optional(
                CONF_CURTAIN1_TARGET,
                default=current_options.get(CONF_CURTAIN1_TARGET)
            ): EntitySelector(EntitySelectorConfig(domain=COVER_DOMAIN)),
            vol.Optional(
                CONF_CURTAIN2_TARGET,
                default=current_options.get(CONF_CURTAIN2_TARGET)
            ): EntitySelector(EntitySelectorConfig(domain=COVER_DOMAIN)),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
        )
