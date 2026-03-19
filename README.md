# Matter Knob Proxy

A custom Home Assistant integration that provides bidirectional synchronization between a Matter knob controller and Home Assistant entities (lights and covers).

## Overview

This integration acts as a proxy between a self-commissioned Matter knob device and existing Home Assistant entities. The knob appears as 4 separate endpoints in Home Assistant via the native Matter integration, and this proxy maps those endpoints to control other devices.

### Supported Endpoints

| Endpoint | Cluster Type | Purpose | Target Domain |
|----------|-------------|---------|---------------|
| 1 | Level Control (0x0008) | Dimmer (Brightness) | `light` |
| 2 | Level Control (0x0008) | CW (Color Temperature) | `light` or `number` |
| 3 | Window Covering (0x0102) | Curtain 1 | `cover` |
| 4 | Window Covering (0x0102) | Curtain 2 | `cover` |

## Features

- **Bidirectional Sync**: Changes made via the knob are reflected on target entities, and changes made via apps/voice are reflected back on the knob's LED ring
- **Debounced Forward Flow**: Prevents event floods during fast knob rotation (100ms debounce)
- **Circular Protection**: Prevents update loops by skipping reverse sync when user is actively controlling (2s window)
- **Multiple Knob Support**: Configure multiple knobs, each controlling different targets
- **Runtime Reconfiguration**: Change mappings without re-commissioning the hardware

## Installation

### Prerequisites

1. Home Assistant with Matter integration configured
2. A Matter knob device with the supported endpoint configuration
3. Target entities (lights and covers) already commissioned in Home Assistant

### Step 1: Copy Files

Copy the `matter_knob_proxy` folder to your Home Assistant `custom_components` directory:

```bash
# Create custom_components if it doesn't exist
mkdir -p /config/custom_components

# Copy the integration
cp -r matter_knob_proxy /config/custom_components/
```

### Step 2: Configure VID/PID (Important!)

Edit `custom_components/matter_knob_proxy/const.py` and update the vendor/product IDs to match your knob's firmware:

```python
DEFAULT_VID = "0xFFF1"  # Replace with your actual Vendor ID
DEFAULT_PID = "0x8001"  # Replace with your actual Product ID
```

If you don't know your VID/PID, you can check the device info in Home Assistant after commissioning the knob via the Matter integration.

### Step 3: Restart Home Assistant

Restart Home Assistant to load the custom integration:

```yaml
# configuration.yaml (if you need to trigger a restart)
homeassistant:
  # Your existing config
```

### Step 4: Commission the Knob (Hardware Setup)

1. Open the Home Assistant Companion App
2. Go to **Settings** → **Devices & Services**
3. Click **Add Integration** → **Matter**
4. Scan the QR code on your knob device
5. The knob will appear as 4 separate entities:
   - `light.knob_dimmer_endpoint_1`
   - `light.knob_cw_endpoint_2` (or number entity)
   - `cover.knob_curtain_1_endpoint_3`
   - `cover.knob_curtain_2_endpoint_4`

### Step 5: Configure the Proxy

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration** → **Matter Knob Proxy**
3. Select your knob device from the dropdown
4. Map each control to a target entity:
   - **Dimmer Control**: Select a light entity (e.g., "Living Room Light")
   - **CW Control**: Select a light or number entity for color temperature
   - **Curtain 1**: Select a cover entity (e.g., "Living Room Curtain")
   - **Curtain 2**: Select a cover entity (e.g., "Bedroom Curtain")
5. Click **Submit**

## Usage

### Direct Control

Rotate the knob to control the mapped light brightness or curtain position. The target entity will update within 200ms.

### Visual Feedback

When you control a target entity via the Home Assistant app, Alexa, or automations, the knob's LED ring will update to reflect the current state (via reverse sync).

### Changing Modes

If your knob firmware supports mode switching (e.g., pressing to cycle between Dimmer/CW/Curtain controls), different targets will respond based on the active mode.

### Reconfiguration

To change target mappings:

1. Go to **Settings** → **Devices & Services**
2. Find **Matter Knob Proxy** and click **Configure**
3. Update the entity mappings
4. Click **Submit** — changes take effect immediately

## Architecture

### Forward Flow (Knob → Target)

```
Knob Rotation → Matter Integration → HA State Change
                                               ↓
                                        [This Integration]
                                               ↓
                                     service_call to Target
```

### Reverse Flow (Target → Knob)

```
App/Voice/Automation → Target State Change
                                               ↓
                                        [This Integration]
                                               ↓
                                     write_attribute to Matter Server
                                               ↓
                                        Knob LED Update
```

### State Conversion

**Level Control (Brightness)**:
- Forward: Matter (0-254) → HA Light (0-255): `round(level * 255 / 254)`
- Reverse: HA Light (0-255) → Matter (0-254): `round(brightness * 254 / 255)`

**Window Covering (Position)**:
- Forward: Matter (0-10000) → HA Cover (0-100): `round(value / 100)`
- Reverse: HA Cover (0-100) → Matter (0-10000): `value * 100`

### Safety Mechanisms

1. **Forward Debounce (100ms)**: Ignores knob state changes that occur within 100ms of the previous change. Prevents flooding during fast rotation.

2. **Circular Protection (2s)**: After a forward flow event, reverse sync is disabled for 2 seconds. This prevents loops where:
   - User rotates knob → Forward to target → Target state changes → Reverse to knob → Knob state changes → Forward to target...

3. **Graceful Degradation**: If a target device is offline, the error is logged but the knob continues to work locally. Commands are not queued indefinitely.

## Troubleshooting

### Knob Not Detected

1. Ensure the knob is commissioned via the Matter integration first
2. Check that `DEFAULT_VID` and `DEFAULT_PID` in `const.py` match your device
3. Look for device name containing "knob" as a fallback match
4. Check Home Assistant logs for discovery messages

### Forward Sync Not Working

1. Verify entity mappings in the integration configuration
2. Check that target entities exist and are available
3. Review logs for service call errors
4. Test the target entity manually to ensure it responds to services

### Reverse Sync Not Working

1. Reverse sync requires communication with the Matter Server
2. Check if the Matter integration exposes a client in `hass.data["matter"]`
3. If using a standalone Matter Server, you may need to implement direct WebSocket communication
4. Check logs for WebSocket connection errors

### Delayed Response

1. The forward flow has a 100ms debounce — this is intentional to prevent floods
2. If response feels sluggish, check target device network connectivity
3. Consider using local push if your target devices support it

## Development

### File Structure

```
custom_components/matter_knob_proxy/
├── __init__.py      # Integration setup, coordinator, event listeners
├── config_flow.py   # UI configuration flow
├── const.py         # Constants (DOMAIN, VID, PID, CLUSTER_IDS)
├── manifest.json    # Integration metadata
├── services.yaml    # Optional manual sync services
└── strings.json     # Translations for UI
```

### Testing Without Hardware

To test the integration without a physical knob:

1. Create mock entities in Home Assistant:
```yaml
# configuration.yaml
light:
  - platform: template
    lights:
      mock_knob_dimmer:
        turn_on:
          - service: persistent_notification.create
            data:
              message: "Knob dimmer turned on"
        turn_off:
          - service: persistent_notification.create
            data:
              message: "Knob dimmer turned off"
```

2. Manually trigger state changes:
```yaml
service: light.turn_on
target:
  entity_id: light.mock_knob_dimmer
data:
  brightness: 128
```

3. Observe the proxy behavior in Home Assistant logs

### Extending the Integration

To add support for additional endpoint types:

1. Add new endpoint constants in `const.py`
2. Update `ENDPOINT_CONFIG_MAP` with the new mapping
3. Add conversion logic in `KnobProxyCoordinator` for forward and reverse flows
4. Update `config_flow.py` to include the new selector

## Known Limitations

1. **Matter Server Dependency**: Reverse sync requires access to the Matter Server WebSocket API. The current implementation attempts to use the matter integration's client, but may need adjustment based on your setup.

2. **No Command Queuing**: If the Matter Server is unavailable, reverse sync commands are not queued. Only the latest state is maintained.

3. **Single Instance Per Knob**: Each physical knob requires its own config entry. Multiple knobs are supported, but each is configured separately.

## Support

For issues, questions, or contributions, please refer to the project's issue tracker or documentation.

## License

This integration is provided as-is for educational and personal use. Modify and distribute according to your needs.
