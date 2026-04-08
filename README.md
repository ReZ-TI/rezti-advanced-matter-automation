# ReZ-TI Matter KnobLink

A professional Home Assistant integration by **ReZ-TI** that provides seamless bidirectional synchronization between Matter knob controllers and Home Assistant entities.

## Overview

Matter KnobLink bridges your Matter-compatible knob controllers with existing Home Assistant devices. The knob appears as native endpoints in Home Assistant via the Matter integration, and KnobLink intelligently maps those endpoints to control your lights, curtains, and more.

### Supported Endpoints

| Endpoint | Cluster Type | Purpose | Target Domain |
|----------|-------------|---------|---------------|
| 1 | Level Control (0x0008) + Color Control (0x0300) | Smart Light (Brightness + Color Temperature) | `light` |
| 3 | Window Covering (0x0102) | Curtain / Shade 1 | `cover` |
| 4 | Window Covering (0x0102) | Curtain / Shade 2 | `cover` |

## Features

- **Bidirectional Sync**: Knob controls targets; app/voice controls update knob LED
- **Smart Debouncing**: 100ms debounce prevents event floods during fast rotation
- **Loop Protection**: 2-second circular protection prevents update loops
- **Multi-Knob Support**: Configure multiple knobs for different zones
- **Hot Reconfiguration**: Change mappings without hardware re-commissioning
- **Selective Forwarding**: Only changed attributes are forwarded (brightness or color temp)

## Installation

### Prerequisites

1. Home Assistant with Matter integration configured
2. A Matter knob device with supported endpoint configuration
3. Target entities (lights and covers) already in Home Assistant

### Step 1: Install via HACS (Recommended)

1. Open HACS → Custom Repositories
2. Add: `https://github.com/rez-ti/matter-knoblink`
3. Install **ReZ-TI Matter KnobLink**
4. Restart Home Assistant

### Step 2: Manual Installation

```bash
# Copy to custom_components
mkdir -p /config/custom_components
cp -r rezti_matter_knoblink /config/custom_components/
```

Restart Home Assistant.

### Step 3: Commission Your Knob

1. Open Home Assistant Companion App
2. **Settings** → **Devices & Services** → **Add Integration** → **Matter**
3. Scan your knob's QR code
4. The knob appears as native entities (light, cover)

### Step 4: Configure KnobLink

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **ReZ-TI Matter KnobLink**
3. Select your knob's source entities
4. Map to target entities:
   - **Dimmer Source** → Light target (controls brightness + color temp)
   - **Curtain 1 Source** → Cover target 1
   - **Curtain 2 Source** → Cover target 2
5. Save — integration reloads automatically

## Usage

### Direct Control

Rotate the knob to control mapped devices. Response time is under 200ms.

### Visual Feedback

When targets are controlled via app, voice, or automations, the knob's LED ring updates automatically.

### Reconfiguration

1. Go to **Settings** → **Devices & Services** → **ReZ-TI Matter KnobLink**
2. Click **Configure**
3. Update mappings
4. Save — changes apply immediately

## Architecture

### Forward Flow (Knob → Target)

```
Knob Rotation → Matter Integration → HA State Change → KnobLink → Target Service Call
```

### Reverse Flow (Target → Knob)

```
App/Voice/Automation → Target State Change → KnobLink → Matter Server → Knob LED
```

### State Conversions

| Attribute | Forward (Knob → HA) | Reverse (HA → Knob) |
|-----------|---------------------|---------------------|
| Brightness | Matter 0-254 → HA 0-255 | HA 0-255 → Matter 0-254 |
| Color Temp | Kelvin (preserved) | Kelvin → Mireds (1,000,000/K) |
| Position | Matter 0-10000 → HA 0-100 | HA 0-100 → Matter 0-10000 |

### Safety Mechanisms

1. **Forward Debounce (100ms)**: Prevents flooding during fast rotation
2. **Circular Protection (2s)**: Breaks feedback loops
3. **Graceful Degradation**: Offline targets don't break the knob

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Knob not detected | Commission via Matter integration first |
| Forward sync fails | Verify source/target entities exist and are available |
| Reverse sync fails | Check Matter Server connectivity |
| Delayed response | Normal — 100ms debounce is intentional |

Enable debug logging:
```yaml
logger:
  logs:
    custom_components.rezti_matter_knoblink: debug
```

## Development

```
custom_components/rezti_matter_knoblink/
├── __init__.py       # Coordinator, event listeners
├── config_flow.py    # UI configuration
├── const.py          # Constants, cluster IDs
├── manifest.json     # Integration metadata
└── strings.json      # UI translations
```

## About Rez-TI

**Rez-TI** creates professional smart home solutions that bridge cutting-edge protocols with elegant user experiences.

## License

MIT License — See LICENSE file for details.
