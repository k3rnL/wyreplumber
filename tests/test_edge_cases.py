import json
import time
import pytest
from wyreplumber._core import WPConnection, WPModule


def test_load_module_without_arguments(pipewire_socket):
    """Test loading a module without arguments."""
    conn = WPConnection()

    # Load a simple module without arguments
    # Note: This might fail if the module requires arguments, but we're testing the API
    module = conn.load_module('libpipewire-module-loopback')

    assert module is not None, "Module should load without arguments"
    assert isinstance(module, WPModule), "Should return WPModule"
    assert module.name == "libpipewire-module-loopback"
    assert module.arguments is None or module.arguments == "", "Arguments should be None or empty"


def test_load_module_with_invalid_name(pipewire_socket):
    """Test loading a module with invalid name."""
    conn = WPConnection()

    # Try to load non-existent module
    with pytest.raises(RuntimeError, match="Failed to load module"):
        conn.load_module('libpipewire-module-does-not-exist-12345')

    # Connection should still be usable after error
    nodes = conn.get_nodes()
    assert isinstance(nodes, list), "Connection should still work after failed module load"


def test_empty_results(pipewire_socket):
    """Test that empty results are returned as empty lists."""
    conn = WPConnection()

    # These should return lists even if empty
    nodes = conn.get_nodes()
    modules = conn.get_modules()
    metadata = conn.get_metadata()

    assert isinstance(nodes, list), "nodes should be a list even if empty"
    assert isinstance(modules, list), "modules should be a list even if empty"
    assert isinstance(metadata, list), "metadata should be a list even if empty"



def test_module_properties_immutability(pipewire_socket):
    """Test that module properties are properly handled."""
    conn = WPConnection()

    args = json.dumps({
        "capture.props": {"node.name": "test_immutable_sink"},
        "playback.props": {"node.name": "test_immutable_playback"}
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Get properties
    props1 = module.properties
    props2 = module.properties

    # Both should be dicts
    assert isinstance(props1, dict)
    assert isinstance(props2, dict)

    # Name should be accessible
    assert module.name is not None


def test_node_properties_access(pipewire_socket):
    """Test various ways to access node properties."""
    conn = WPConnection()

    # Create a node
    args = json.dumps({
        "capture.props": {
            "node.name": "test_access_sink",
            "node.description": "Test access",
            "media.class": "Audio/Sink"
        },
        "playback.props": {"node.name": "test_access_playback"}
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_access_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()


    assert test_node is not None

    # Test various property access patterns
    props = test_node.properties

    # .get() with default
    name = props.get("node.name", "default")
    assert name == "test_access_sink"

    # .get() for non-existent key
    non_existent = props.get("nonexistent.key")
    assert non_existent is None

    # .get() with default for non-existent key
    with_default = props.get("nonexistent.key", "my_default")
    assert with_default == "my_default"

    # Test in operator
    assert "node.name" in props
    assert "nonexistent.key" not in props


def test_sync_between_operations(pipewire_socket):
    """Test sync behavior between different operations."""
    conn = WPConnection()

    # Operation 1
    nodes1 = conn.get_nodes()
    conn.sync()

    # Operation 2
    modules = conn.get_modules()
    conn.sync()

    # Operation 3
    nodes2 = conn.get_nodes()
    conn.sync()

    # All should succeed
    assert isinstance(nodes1, list)
    assert isinstance(modules, list)
    assert isinstance(nodes2, list)



def test_metadata_edge_cases(pipewire_socket):
    """Test metadata edge cases."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    if len(metadata_list) > 0:
        metadata = metadata_list[0]

        # Test find with non-existent subject/key
        result = metadata.find(99999, "nonexistent.key")
        assert result is None, "Should return None for non-existent metadata"

        # Test iterate with non-existent subject
        items = metadata.iterate(subject=99999)
        assert isinstance(items, list), "Should return list even for non-existent subject"



def test_port_direction_edge_cases(pipewire_socket):
    """Test port direction with edge cases."""
    conn = WPConnection()

    # Create a node
    args = json.dumps({
        "capture.props": {"node.name": "test_port_edge_sink"},
        "playback.props": {"node.name": "test_port_edge_playback"}
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_port_edge_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()


    if test_node:
        # Test with None direction (should get all ports)
        all_ports = test_node.get_ports(direction=None)
        assert isinstance(all_ports, list)

        # Test with valid directions
        input_ports = test_node.get_ports(direction=0)  # WP_DIRECTION_INPUT
        output_ports = test_node.get_ports(direction=1)  # WP_DIRECTION_OUTPUT

        assert isinstance(input_ports, list)
        assert isinstance(output_ports, list)