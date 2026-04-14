import json
import time
import pytest
from wyreplumber._core import WPConnection


def test_wparam_get_parsed(pipewire_socket):
    """Test WPParam.get() with parsing enabled (default)."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "capture.props": {
            "node.name": "test_spa_parsing",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_spa_parsing_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_spa_parsing":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get params
    params = test_node.get_params()
    assert len(params) > 0, "Should have params"

    # Test parsing on params that have values
    found_parsed = False
    for param_id, param_obj in params.items():
        if 'r' not in param_obj.permissions:
            continue

        # Get parsed values (default behavior)
        parsed_values = param_obj.get()
        assert isinstance(parsed_values, list), "Should return a list"

        # Get raw values
        raw_values = param_obj.get(parse=False)
        assert isinstance(raw_values, list), "Should return a list"

        # If we have values, verify parsing worked
        if len(parsed_values) > 0:
            print(f"\n{param_id} parsed values:")
            for i, val in enumerate(parsed_values):
                print(f"  [{i}]: {type(val).__name__} = {val}")

            print(f"\n{param_id} raw values:")
            for i, val in enumerate(raw_values):
                print(f"  [{i}]: {val}")

            # Parsed values should not be the same type as raw
            # Raw values are dicts with 'type', 'size', 'data'
            # Parsed values should be Python types (dict, list, int, float, str, etc.)
            if isinstance(raw_values[0], dict) and 'data' in raw_values[0]:
                # This is a raw value - parsed should be different
                assert parsed_values[0] != raw_values[0], "Parsed should differ from raw"
                found_parsed = True

    assert found_parsed, "Should have found at least one param with parsed values"


def test_wparam_explicit_parse_modes(pipewire_socket):
    """Test explicit parse=True and parse=False."""
    conn = WPConnection()

    args = json.dumps({
        "capture.props": {
            "node.name": "test_parse_modes",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_parse_modes_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_parse_modes":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None

    params = test_node.get_params()

    for param_id, param_obj in params.items():
        values_default = param_obj.get()
        values_parse_true = param_obj.get(parse=True)
        values_parse_false = param_obj.get(parse=False)

        assert isinstance(values_default, list)
        assert isinstance(values_parse_true, list)
        assert isinstance(values_parse_false, list)

        # Default should equal explicit parse=True
        assert len(values_default) == len(values_parse_true)


def test_spa_pod_module_exists(pipewire_socket):
    """Test that spa_pod module is importable."""
    from wyreplumber import spa_pod

    # Check that parsing functions exist
    assert hasattr(spa_pod, 'parse_spa_pod')
    assert hasattr(spa_pod, 'parse_spa_pod_dict')

    # Test parsing a simple int pod
    import struct
    pod_data = struct.pack('<II', 4, 4) + struct.pack('<i', 42) + b'\x00' * 4
    result = spa_pod.parse_spa_pod(pod_data, 0)
    assert result == 42, f"Expected 42, got {result}"

    # Test parsing via dict
    pod_dict = {'type': 4, 'size': 4, 'data': pod_data}
    result = spa_pod.parse_spa_pod_dict(pod_dict)
    assert result == 42, f"Expected 42, got {result}"
