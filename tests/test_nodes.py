import json
import time
import pytest
from wyreplumber._core import (
    WPConnection,
    WPNode,
    WPPort,
    WP_NODE_STATE_ERROR,
    WP_NODE_STATE_CREATING,
    WP_NODE_STATE_SUSPENDED,
    WP_NODE_STATE_IDLE,
    WP_NODE_STATE_RUNNING,
    WP_DIRECTION_INPUT,
    WP_DIRECTION_OUTPUT,
)


def test_get_nodes(pipewire_socket):
    """Test getting list of nodes."""
    conn = WPConnection()
    nodes = conn.get_nodes()

    assert isinstance(nodes, list), "nodes should be a list"
    for node in nodes:
        assert isinstance(node, WPNode), "Each item should be a WPNode"



def test_node_properties(pipewire_socket):
    """Test node properties."""
    conn = WPConnection()

    # Create a test node via module
    args = json.dumps({
        "node.description": "Test node properties",
        "capture.props": {
            "node.name": "test_props_sink",
            "node.description": "Test properties sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_props_sink_playback",
            "node.description": "Test properties playback"
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_props_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Test node properties
    assert isinstance(test_node.id, int), "Node ID should be an integer"
    assert test_node.id > 0, "Node ID should be positive"

    assert isinstance(test_node.properties, dict), "Properties should be a dict"
    assert test_node.properties.get("node.name") == "test_props_sink", "Node name should match"
    assert test_node.properties.get("node.description") == "Test properties sink", "Description should match"
    assert test_node.properties.get("media.class") == "Audio/Sink", "Media class should match"

    # Test node state
    assert isinstance(test_node.state, int), "State should be an integer"
    assert test_node.state in [
        WP_NODE_STATE_ERROR,
        WP_NODE_STATE_CREATING,
        WP_NODE_STATE_SUSPENDED,
        WP_NODE_STATE_IDLE,
        WP_NODE_STATE_RUNNING,
    ], "State should be a valid node state"

    # Test port counts
    assert isinstance(test_node.n_input_ports, int), "n_input_ports should be an integer"
    assert isinstance(test_node.max_input_ports, int), "max_input_ports should be an integer"
    assert isinstance(test_node.n_output_ports, int), "n_output_ports should be an integer"
    assert isinstance(test_node.max_output_ports, int), "max_output_ports should be an integer"

    assert test_node.n_input_ports >= 0, "n_input_ports should be non-negative"
    assert test_node.max_input_ports >= 0, "max_input_ports should be non-negative"
    assert test_node.n_output_ports >= 0, "n_output_ports should be non-negative"
    assert test_node.max_output_ports >= 0, "max_output_ports should be non-negative"

    # Test error message (should be None for non-error states)
    if test_node.state != WP_NODE_STATE_ERROR:
        assert test_node.error_message is None, "Error message should be None when not in error state"


def test_node_get_ports(pipewire_socket):
    """Test getting ports from a node."""
    conn = WPConnection()

    # Create a test node via module
    args = json.dumps({
        "node.description": "Test node ports",
        "capture.props": {
            "node.name": "test_ports_sink",
            "media.class": "Audio/Sink",
            "audio.position": "FL,FR"  # Create 2 ports
        },
        "playback.props": {
            "node.name": "test_ports_sink_playback",
            "audio.position": "FL,FR"
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes to appear and get ports
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_ports_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get all ports
    all_ports = test_node.get_ports()
    assert isinstance(all_ports, list), "get_ports() should return a list"
    for port in all_ports:
        assert isinstance(port, WPPort), "Each port should be a WPPort instance"

    # Get input ports
    input_ports = test_node.get_ports(direction=WP_DIRECTION_INPUT)
    assert isinstance(input_ports, list), "get_ports(INPUT) should return a list"
    for port in input_ports:
        assert port.direction == WP_DIRECTION_INPUT, "All ports should be input ports"

    # Get output ports
    output_ports = test_node.get_ports(direction=WP_DIRECTION_OUTPUT)
    assert isinstance(output_ports, list), "get_ports(OUTPUT) should return a list"
    for port in output_ports:
        assert port.direction == WP_DIRECTION_OUTPUT, "All ports should be output ports"

    # Verify counts match
    assert len(input_ports) + len(output_ports) == len(all_ports), "Input + output ports should equal all ports"

    # Test invalid direction
    with pytest.raises((ValueError, TypeError)):
        test_node.get_ports(direction=999)


def test_node_delete(pipewire_socket):
    """Test deleting a node."""
    conn = WPConnection()

    # Create a test node via module
    args = json.dumps({
        "node.description": "Test node delete",
        "capture.props": {
            "node.name": "test_delete_sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_delete_sink_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_delete_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"
    node_id = test_node.id

    # Delete the node
    test_node.delete()
    conn.sync()
    time.sleep(0.5)

    # Verify node is gone
    nodes = conn.get_nodes()
    node_ids = [n.id for n in nodes]
    assert node_id not in node_ids, "Node should be deleted"

    # Trying to delete again should raise an error
    with pytest.raises(RuntimeError, match="already deleted or invalid"):
        test_node.delete()


def test_node_state_constants(pipewire_socket):
    """Test that node state constants are defined."""
    assert WP_NODE_STATE_ERROR == -1
    assert WP_NODE_STATE_CREATING == 0
    assert WP_NODE_STATE_SUSPENDED == 1
    assert WP_NODE_STATE_IDLE == 2
    assert WP_NODE_STATE_RUNNING == 3
