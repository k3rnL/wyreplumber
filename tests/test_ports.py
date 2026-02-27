import json
import time
from wyreplumber._core import (
    WPConnection,
    WPPort,
    WP_DIRECTION_INPUT,
    WP_DIRECTION_OUTPUT,
)


def test_port_properties(pipewire_socket):
    """Test port properties."""
    conn = WPConnection()

    # Create a test node with ports
    args = json.dumps({
        "node.description": "Test port properties",
        "capture.props": {
            "node.name": "test_port_props_sink",
            "media.class": "Audio/Sink",
            "audio.position": "FL,FR"
        },
        "playback.props": {
            "node.name": "test_port_props_playback",
            "audio.position": "FL,FR"
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes and get ports
    deadline = time.time() + 2.0
    test_ports = []
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_port_props_sink":
                test_ports = node.get_ports()
                break
        if test_ports:
            break
        conn.sync()

    assert len(test_ports) > 0, "Should have at least one port"

    # Test port properties
    for port in test_ports:
        assert isinstance(port, WPPort), "Port should be a WPPort instance"

        # Test ID
        assert isinstance(port.id, int), "Port ID should be an integer"
        assert port.id > 0, "Port ID should be positive"

        # Test properties
        assert isinstance(port.properties, dict), "Properties should be a dict"
        assert "port.name" in port.properties or "port.id" in port.properties, "Should have port.name or port.id"

        # Test direction
        assert isinstance(port.direction, int), "Direction should be an integer"
        assert port.direction in [WP_DIRECTION_INPUT, WP_DIRECTION_OUTPUT], "Direction should be INPUT or OUTPUT"


def test_port_direction_constants(pipewire_socket):
    """Test that port direction constants are defined."""
    assert WP_DIRECTION_INPUT == 0
    assert WP_DIRECTION_OUTPUT == 1


def test_port_filtering_by_direction(pipewire_socket):
    """Test that port filtering by direction works correctly."""
    conn = WPConnection()

    # Create a test node with both input and output ports
    args = json.dumps({
        "node.description": "Test port filtering",
        "capture.props": {
            "node.name": "test_port_filter_sink",
            "media.class": "Audio/Sink",
            "audio.position": "FL,FR"
        },
        "playback.props": {
            "node.name": "test_port_filter_playback",
            "audio.position": "FL,FR"
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_port_filter_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get ports by direction
    input_ports = test_node.get_ports(direction=WP_DIRECTION_INPUT)
    output_ports = test_node.get_ports(direction=WP_DIRECTION_OUTPUT)
    all_ports = test_node.get_ports()

    # Verify all input ports have correct direction
    for port in input_ports:
        assert port.direction == WP_DIRECTION_INPUT, "Input port should have INPUT direction"

    # Verify all output ports have correct direction
    for port in output_ports:
        assert port.direction == WP_DIRECTION_OUTPUT, "Output port should have OUTPUT direction"

    # Verify totals match
    assert len(input_ports) + len(output_ports) == len(all_ports), "Sum of filtered ports should equal all ports"