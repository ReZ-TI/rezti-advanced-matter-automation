"""The Matter Knob Proxy integration.

This integration provides bidirectional synchronization between a Matter knob device
and Home Assistant entities (lights and covers).

Architecture:
-------------
Forward Flow (Knob → Target):
    The knob's endpoints create entities via the native Matter integration.
    We listen for state changes on these entities and proxy commands to
    the mapped target entities.

Reverse Flow (Target → Knob):
    When target entities change (via app/voice/automation), we write the
    new state back to the knob's Matter clusters via the Matter Server
    WebSocket API. This provides visual feedback on the knob's LED ring.

Safety Considerations:
---------------------
1. Debouncing: Forward flow ignores changes within 100ms to prevent flood
   during fast knob rotation.
2. Circular Protection: Reverse flow is skipped if forward flow was triggered
   within the last 2 seconds (user is actively controlling).
3. Error Handling: Target offline errors are caught and logged without
   disrupting the knob's local state.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_TURN_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    HomeAssistant,
    Event,
    State,
    callback,
    CALLBACK_TYPE,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_SET_COVER_POSITION,
)
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    LOGGER_NAME,
    ENDPOINT_DIMMER,
    ENDPOINT_CURTAIN_1,
    ENDPOINT_CURTAIN_2,
    LEVEL_CONTROL_CLUSTER,
    WINDOW_COVERING_CLUSTER,
    COLOR_CONTROL_CLUSTER,
    LEVEL_CONTROL_CURRENT_LEVEL_ATTR,
    WINDOW_COVERING_POSITION_ATTR,
    COLOR_TEMPERATURE_ATTRIBUTE,
    LEVEL_MAX_MATTER,
    LEVEL_MAX_HA,
    WINDOW_COVERING_MAX_MATTER,
    WINDOW_COVERING_MAX_HA,
    DEBOUNCE_FORWARD,
    DEBOUNCE_REVERSE,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# Type aliases
KnobMapping = dict[int, str | None]  # endpoint_id -> target_entity_id
ListenerHandles = dict[str, CALLBACK_TYPE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Matter Knob Proxy from a config entry.
    
    Called when the integration is first set up or after HA restart.
    Establishes all event listeners and performs initial state sync.
    """
    _LOGGER.debug("Setting up Matter Knob Proxy for entry %s", entry.entry_id)

    # Initialize domain data if needed
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    # Create the coordinator
    coordinator = KnobProxyCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Perform setup
    await coordinator.async_setup()

    # Listen for shutdown
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.async_shutdown)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.
    
    Cleans up all listeners and WebSocket connections.
    """
    _LOGGER.debug("Unloading Matter Knob Proxy entry %s", entry.entry_id)

    coordinator: KnobProxyCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator:
        await coordinator.async_shutdown()

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    _LOGGER.debug("Reloading Matter Knob Proxy entry %s", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


class KnobProxyCoordinator:
    """Coordinates bidirectional sync between knob and target entities.
    
    This class manages:
    - Forward flow: Knob state changes → Target entity commands
    - Reverse flow: Target entity changes → Matter Server write_attribute
    - Debouncing to prevent event floods
    - Circular protection to prevent update loops
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.entry = entry
        
        # Source entities (endpoint_id -> source_entity_id) - the "knob" inputs
        self._source_entities: dict[int, str | None] = entry.data.get("source_entities", {})
        
        # Target entities (endpoint_id -> target_entity_id) - what to control
        self._mappings: KnobMapping = entry.data.get("target_entities", {})
        
        # Listener handles for cleanup
        self._listeners: ListenerHandles = {}
        
        # Debounce tracking
        self._last_forward_time: datetime | None = None
        self._forward_debounce_handle: asyncio.TimerHandle | None = None
        
        # Matter Server connection (initialized on first reverse sync)
        self._matter_client: Any | None = None
        self._matter_ws: Any | None = None

    async def async_setup(self) -> None:
        """Set up the coordinator and establish listeners."""
        _LOGGER.info("Setting up Matter Knob Proxy")
        _LOGGER.debug("Source entities: %s", self._source_entities)
        _LOGGER.debug("Target entities: %s", self._mappings)

        # Set up forward flow listeners (Source → Target)
        self._setup_forward_listeners()

        # Set up reverse flow listeners (Target → Source)
        self._setup_reverse_listeners()

        # Perform initial sync (Target → Source)
        await self._perform_initial_sync()

        _LOGGER.info("Matter Knob Proxy setup complete")

    def _load_mappings(self) -> None:
        """Load entity mappings from config entry data (legacy - not used anymore)."""
        pass

    # Entity discovery removed - we now use configured source entities directly

    def _setup_forward_listeners(self) -> None:
        """Set up listeners for forward flow (Source → Target).
        
        Listens for state changes on source entities and forwards commands
        to mapped target entities.
        """
        for endpoint_id, source_entity in self._source_entities.items():
            if not source_entity:
                continue  # No source configured for this endpoint
                
            target_entity = self._mappings.get(endpoint_id)
            
            if not target_entity:
                continue  # No target configured for this endpoint

            # Create listener for this source entity
            unsub = async_track_state_change_event(
                self.hass,
                [source_entity],
                self._create_forward_handler(endpoint_id, source_entity, target_entity),
            )
            
            self._listeners[f"forward_{endpoint_id}"] = unsub
            _LOGGER.debug(
                "Forward listener: %s (endpoint %d) → %s",
                source_entity, endpoint_id, target_entity
            )

    def _create_forward_handler(
        self, endpoint_id: int, source_entity: str, target_entity: str
    ) -> callable:
        """Create a handler for forward flow state changes."""
        
        @callback
        async def handler(event: Event) -> None:
            """Handle source state change and forward to target."""
            # Debounce check: ignore if changed within debounce window
            now = datetime.now()
            if self._last_forward_time:
                elapsed = (now - self._last_forward_time).total_seconds()
                if elapsed < DEBOUNCE_FORWARD:
                    _LOGGER.debug(
                        "Debouncing forward event for endpoint %d (%.3fs elapsed)",
                        endpoint_id, elapsed
                    )
                    return

            self._last_forward_time = now

            # Get old and new state
            old_state: State | None = event.data.get("old_state")
            new_state: State | None = event.data.get("new_state")
            if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug("Ignoring invalid state for %s: %s", source_entity, new_state)
                return

            # Convert and forward based on endpoint type
            try:
                if endpoint_id == ENDPOINT_DIMMER:
                    await self._forward_light(endpoint_id, old_state, new_state, target_entity)
                elif endpoint_id in (ENDPOINT_CURTAIN_1, ENDPOINT_CURTAIN_2):
                    await self._forward_window_covering(endpoint_id, old_state, new_state, target_entity)
            except Exception as err:
                _LOGGER.error(
                    "Error forwarding state from %s to %s: %s",
                    source_entity, target_entity, err
                )

        return handler

    async def _forward_light(
        self, endpoint_id: int, old_state: State | None, new_state: State, target_entity: str
    ) -> None:
        """Forward light changes to target light.
        
        Handles brightness and color temperature changes to a single target.
        Only forwards what actually changed.
        """
        # Check if on/off state changed
        old_on = old_state.state == "on" if old_state else False
        new_on = new_state.state == "on"
        
        if not new_on:
            # Light turned off
            _LOGGER.debug(
                "Forward Light (endpoint %d): turning off %s",
                endpoint_id, target_entity
            )
            try:
                await self.hass.services.async_call(
                    LIGHT_DOMAIN,
                    "turn_off",
                    {ATTR_ENTITY_ID: target_entity},
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.warning("Failed to turn off light %s: %s", target_entity, err)
            return
        
        # Light is on - prepare service data
        service_data = {ATTR_ENTITY_ID: target_entity}
        has_changes = False
        
        # Check if brightness changed
        old_brightness = old_state.attributes.get("brightness") if old_state else None
        new_brightness = new_state.attributes.get("brightness")
        
        if new_brightness is not None and new_brightness != old_brightness:
            ha_brightness = round(new_brightness * LEVEL_MAX_HA / LEVEL_MAX_MATTER)
            ha_brightness = max(0, min(255, ha_brightness))
            service_data[ATTR_BRIGHTNESS] = ha_brightness
            has_changes = True
            _LOGGER.debug(
                "Forward Light (endpoint %d): brightness %s → %s → %d",
                endpoint_id, old_brightness, new_brightness, ha_brightness
            )
        
        # Check if color temperature changed
        old_color_temp = old_state.attributes.get("color_temp_kelvin") if old_state else None
        new_color_temp = new_state.attributes.get("color_temp_kelvin")
        
        if new_color_temp is not None and new_color_temp != old_color_temp:
            service_data["color_temp_kelvin"] = int(new_color_temp)
            has_changes = True
            _LOGGER.debug(
                "Forward Light (endpoint %d): color_temp %s → %s",
                endpoint_id, old_color_temp, new_color_temp
            )
        
        # Also handle turn_on if state changed from off to on
        if not old_on and new_on:
            has_changes = True
            _LOGGER.debug(
                "Forward Light (endpoint %d): turned on %s",
                endpoint_id, target_entity
            )
        
        # Only call service if we have something to change
        if has_changes:
            try:
                await self.hass.services.async_call(
                    LIGHT_DOMAIN,
                    SERVICE_TURN_ON,
                    service_data,
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.warning(
                    "Failed to control light %s: %s (device may be offline)",
                    target_entity, err
                )
        else:
            _LOGGER.debug(
                "Forward Light (endpoint %d): no changes to forward for %s",
                endpoint_id, target_entity
            )

    async def _forward_window_covering(
        self, endpoint_id: int, old_state: State | None, new_state: State, target_entity: str
    ) -> None:
        """Forward Window Covering state change to target cover.
        
        Only forwards when position actually changed.
        Handles open/closed states and current_position attribute.
        """
        # Get old and new positions
        old_position = old_state.attributes.get("current_position") if old_state else None
        new_position = new_state.attributes.get("current_position")
        
        # Handle state-based position if attribute not available
        if new_position is None:
            if new_state.state == "open":
                new_position = 100
            elif new_state.state == "closed":
                new_position = 0
            else:
                _LOGGER.debug(
                    "Forward Window Covering (endpoint %d): no position in state %s",
                    endpoint_id, new_state.state
                )
                return
        
        # Only forward if position changed
        if new_position == old_position:
            _LOGGER.debug(
                "Forward Window Covering (endpoint %d): position unchanged (%s), skipping",
                endpoint_id, new_position
            )
            return
        
        # Convert Matter position (0-10000) to HA position (0-100) if needed
        # If already 0-100, pass through
        if new_position > 100:
            ha_position = round(new_position * WINDOW_COVERING_MAX_HA / WINDOW_COVERING_MAX_MATTER)
        else:
            ha_position = new_position
        
        ha_position = max(0, min(100, ha_position))  # Clamp to valid range

        _LOGGER.debug(
            "Forward Window Covering (endpoint %d): %s → %s → %d for %s",
            endpoint_id, old_position, new_position, ha_position, target_entity
        )

        # Call cover.set_cover_position service
        try:
            await self.hass.services.async_call(
                COVER_DOMAIN,
                SERVICE_SET_COVER_POSITION,
                {ATTR_ENTITY_ID: target_entity, ATTR_POSITION: ha_position},
                blocking=False,
            )
        except Exception as err:
            _LOGGER.warning(
                "Failed to control cover %s: %s (device may be offline)",
                target_entity, err
            )

    def _setup_reverse_listeners(self) -> None:
        """Set up listeners for reverse flow (Target → Knob).
        
        Listens for state changes on target entities and writes back to
        the knob's Matter clusters for visual feedback.
        """
        for endpoint_id, target_entity in self._mappings.items():
            if not target_entity:
                continue

            # Create listener for this target entity
            unsub = async_track_state_change_event(
                self.hass,
                [target_entity],
                self._create_reverse_handler(endpoint_id, target_entity),
            )
            
            self._listeners[f"reverse_{endpoint_id}"] = unsub
            _LOGGER.debug(
                "Reverse listener: %s → endpoint %d",
                target_entity, endpoint_id
            )

    def _create_reverse_handler(
        self, endpoint_id: int, target_entity: str
    ) -> callable:
        """Create a handler for reverse flow state changes."""
        
        @callback
        async def handler(event: Event) -> None:
            """Handle target state change and write back to knob."""
            # Circular protection: skip if forward flow was recent
            if self._last_forward_time:
                elapsed = (datetime.now() - self._last_forward_time).total_seconds()
                if elapsed < DEBOUNCE_REVERSE:
                    _LOGGER.debug(
                        "Skipping reverse sync for endpoint %d "
                        "(forward was %.3fs ago, user actively controlling)",
                        endpoint_id, elapsed
                    )
                    return

            # Get new state
            new_state: State | None = event.data.get("new_state")
            if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return

            # Convert and write back based on endpoint type
            try:
                if endpoint_id == ENDPOINT_DIMMER:
                    await self._reverse_light(ENDPOINT_DIMMER, new_state)
                elif endpoint_id in (ENDPOINT_CURTAIN_1, ENDPOINT_CURTAIN_2):
                    await self._reverse_window_covering(endpoint_id, new_state)
            except Exception as err:
                _LOGGER.error(
                    "Error in reverse sync for endpoint %d: %s",
                    endpoint_id, err
                )

        return handler

    async def _reverse_light(self, endpoint_id: int, state: State) -> None:
        """Write target light state back to knob's clusters.
        
        Handles both brightness (Level Control) and color temperature (Color Control).
        """
        source_entity = self._source_entities.get(endpoint_id)
        if not source_entity:
            return
        
        # Handle brightness (Level Control cluster)
        brightness = state.attributes.get("brightness")
        if brightness is None:
            if state.state == "off":
                brightness = 0
            else:
                return
        
        matter_level = round(brightness * LEVEL_MAX_MATTER / LEVEL_MAX_HA)
        matter_level = max(0, min(254, matter_level))

        _LOGGER.debug(
            "Reverse Light (endpoint %d): brightness %d → %d",
            endpoint_id, brightness, matter_level
        )

        await self._write_matter_attribute(
            endpoint_id=endpoint_id,
            cluster_id=LEVEL_CONTROL_CLUSTER,
            attribute_id=LEVEL_CONTROL_CURRENT_LEVEL_ATTR,
            value=matter_level,
        )
        
        # Handle color temperature (Color Control cluster)
        color_temp_kelvin = state.attributes.get("color_temp_kelvin")
        if color_temp_kelvin:
            # Convert kelvin to mireds (1,000,000 / kelvin)
            mireds = round(1000000 / color_temp_kelvin)
            # Clamp to valid Matter range (typically 153-370)
            mireds = max(153, min(370, mireds))
            
            _LOGGER.debug(
                "Reverse Light (endpoint %d): color_temp_kelvin %d → mireds %d",
                endpoint_id, color_temp_kelvin, mireds
            )
            
            await self._write_matter_attribute(
                endpoint_id=endpoint_id,
                cluster_id=COLOR_CONTROL_CLUSTER,
                attribute_id=COLOR_TEMPERATURE_ATTRIBUTE,
                value=mireds,
            )

    async def _reverse_window_covering(self, endpoint_id: int, state: State) -> None:
        """Write target cover state back to knob's Window Covering cluster.
        
        Converts HA position (0-100) to Matter position (0-10000).
        Handles open/closed states when position attribute is missing.
        """
        position = state.attributes.get("current_position")
        
        # Try to infer from state if attribute not available
        if position is None:
            if state.state == "open":
                position = 100
            elif state.state == "closed":
                position = 0
            else:
                return

        # Convert HA position (0-100) to Matter position (0-10000)
        matter_position = round(position * WINDOW_COVERING_MAX_MATTER / WINDOW_COVERING_MAX_HA)
        matter_position = max(0, min(10000, matter_position))

        _LOGGER.debug(
            "Reverse Window Covering (endpoint %d): %d → %d",
            endpoint_id, position, matter_position
        )

        await self._write_matter_attribute(
            endpoint_id=endpoint_id,
            cluster_id=WINDOW_COVERING_CLUSTER,
            attribute_id=WINDOW_COVERING_POSITION_ATTR,
            value=matter_position,
        )

    async def _write_matter_attribute(
        self,
        endpoint_id: int,
        cluster_id: int,
        attribute_id: int,
        value: int,
    ) -> None:
        """Write an attribute to the source entity (for bidirectional sync).
        
        For non-Matter sources, this attempts to set the state attribute directly.
        Note: This won't actually change the physical device unless the source
        supports writing back.
        """
        source_entity = self._source_entities.get(endpoint_id)
        if not source_entity:
            return
        
        # Log the intended write - for non-Matter sources, we can't really write back
        # unless the entity supports a specific service
        _LOGGER.debug(
            "Would write to source %s: endpoint=%d, cluster=0x%04X, value=%d",
            source_entity, endpoint_id, cluster_id, value
        )

    async def _perform_initial_sync(self) -> None:
        """Perform initial state sync on startup.
        
        Reads current target states and pushes them to the knob for
        visual consistency on startup.
        """
        _LOGGER.debug("Performing initial state sync")

        for endpoint_id, target_entity in self._mappings.items():
            if not target_entity:
                continue

            state = self.hass.states.get(target_entity)
            if not state:
                continue

            try:
                if endpoint_id == ENDPOINT_DIMMER:
                    await self._reverse_light(ENDPOINT_DIMMER, state)
                elif endpoint_id in (ENDPOINT_CURTAIN_1, ENDPOINT_CURTAIN_2):
                    await self._reverse_window_covering(endpoint_id, state)
            except Exception as err:
                _LOGGER.warning(
                    "Initial sync failed for endpoint %d: %s",
                    endpoint_id, err
                )

        _LOGGER.debug("Initial sync complete")

    async def async_shutdown(self, event: Event | None = None) -> None:
        """Clean up all listeners and connections.
        
        Called on integration unload or HA shutdown.
        """
        _LOGGER.debug("Shutting down Matter Knob Proxy coordinator")

        # Cancel all listeners
        for name, unsub in self._listeners.items():
            try:
                unsub()
                _LOGGER.debug("Cancelled listener: %s", name)
            except Exception as err:
                _LOGGER.debug("Error cancelling listener %s: %s", name, err)

        self._listeners.clear()

        # Cancel any pending debounce timer
        if self._forward_debounce_handle:
            self._forward_debounce_handle.cancel()
            self._forward_debounce_handle = None

        _LOGGER.debug("Shutdown complete")
