"""Constants for the Matter Knob Proxy integration."""

DOMAIN = "matter_knob_proxy"

# Matter Vendor and Product IDs for the knob device
# These should match your hardware firmware
DEFAULT_VID = "0xFFF1"  # Test Vendor ID (replace with your actual VID)
DEFAULT_PID = "0x8001"  # Test Product ID (replace with your actual PID)

# Matter Cluster IDs
LEVEL_CONTROL_CLUSTER = 0x0008
WINDOW_COVERING_CLUSTER = 0x0102

# Matter Attribute IDs
LEVEL_CONTROL_CURRENT_LEVEL_ATTR = 0x0000  # CurrentLevel attribute
WINDOW_COVERING_POSITION_ATTR = 0x000E  # CurrentPositionLiftPercent100ths attribute

# Endpoint identifiers (as defined in firmware)
ENDPOINT_DIMMER = 1  # Level Control - Dimmer
ENDPOINT_CW = 2      # Level Control - CW (Color Temperature)
ENDPOINT_CURTAIN_1 = 3  # Window Covering - Curtain 1
ENDPOINT_CURTAIN_2 = 4  # Window Covering - Curtain 2

# Configuration keys
CONF_KNOB_DEVICE_ID = "knob_device_id"
CONF_KNOB_NODE_ID = "knob_node_id"
CONF_DIMMER_TARGET = "dimmer_target"
CONF_CW_TARGET = "cw_target"
CONF_CURTAIN1_TARGET = "curtain1_target"
CONF_CURTAIN2_TARGET = "curtain2_target"

# Mapping of endpoint IDs to config keys
ENDPOINT_CONFIG_MAP = {
    ENDPOINT_DIMMER: CONF_DIMMER_TARGET,
    ENDPOINT_CW: CONF_CW_TARGET,
    ENDPOINT_CURTAIN_1: CONF_CURTAIN1_TARGET,
    ENDPOINT_CURTAIN_2: CONF_CURTAIN2_TARGET,
}

# Debounce intervals (seconds)
DEBOUNCE_FORWARD = 0.1   # Ignore knob changes within 100ms
DEBOUNCE_REVERSE = 2.0   # Skip reverse sync if forward was triggered within 2s

# Matter Server connection
MATTER_SERVER_WS_PORT = 5580
MATTER_SERVER_DEFAULT_HOST = "localhost"

# Conversion factors
LEVEL_MAX_MATTER = 254
LEVEL_MAX_HA = 255
WINDOW_COVERING_MAX_MATTER = 10000
WINDOW_COVERING_MAX_HA = 100

# Logger name
LOGGER_NAME = __name__
