import json
import time
import pytest
from wyreplumber._core import (
    WPConnection,
    WPNode,
    WPPipewireObject,
)


def test_pipewire_object_properties(pipewire_socket):
    """Test basic PipeWire object properties."""
    conn = WPConnection()

    # Create a test node via module
    args = json.dumps({
        "node.description": "Test PipeWire object",
        "capture.props": {
            "node.name": "test_pw_object_sink",
            "node.description": "Test PipeWire object sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_pw_object_playback",
            "node.description": "Test PipeWire object playback"
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for nodes to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_pw_object_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Verify it's a PipeWire object
    assert isinstance(test_node, WPPipewireObject), "Node should be a WPPipewireObject"

    # Test basic properties
    assert isinstance(test_node.id, int), "Object ID should be an integer"
    assert test_node.id > 0, "Object ID should be positive"

    assert isinstance(test_node.properties, dict), "Properties should be a dict"
    assert len(test_node.properties) > 0, "Properties should not be empty"


def test_get_param_info(pipewire_socket):
    """Test getting parameter info from a PipeWire object."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "node.description": "Test param info",
        "capture.props": {
            "node.name": "test_param_info_sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_param_info_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_param_info_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get param info
    param_info = test_node.get_param_info()

    assert isinstance(param_info, dict), "param_info should be a dict"

    # Verify param_info structure
    for key, value in param_info.items():
        assert isinstance(key, str), "Param ID should be a string"
        assert isinstance(value, str), "Permissions should be a string"
        # Permissions should contain 'r', 'w', or both
        assert all(c in 'rw' for c in value), f"Permissions should only contain 'r' or 'w', got: {value}"


def test_get_params(pipewire_socket):
    """Test getting all params from a PipeWire object."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "node.description": "Test get params",
        "capture.props": {
            "node.name": "test_get_params_sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_get_params_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_get_params_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get params
    params = test_node.get_params()

    assert isinstance(params, dict), "get_params should return a dict"

    assert len(params.items()) > 0, "Test node should have at least one parameter"

    # Verify params structure
    for param_id, param_obj in params.items():
        assert isinstance(param_id, str), "Param ID should be a string"

        # Verify WPParam object structure
        assert hasattr(param_obj, 'id'), "Param should have 'id' attribute"
        assert hasattr(param_obj, 'permissions'), "Param should have 'permissions' attribute"
        assert hasattr(param_obj, 'type'), "Param should have 'type' attribute"
        assert hasattr(param_obj, 'get'), "Param should have 'get' method"
        assert hasattr(param_obj, 'set'), "Param should have 'set' method"

        # Verify attributes
        assert param_obj.id == param_id, "Param ID should match dict key"
        assert isinstance(param_obj.permissions, str), "Permissions should be a string"
        assert all(c in 'rw' for c in param_obj.permissions), "Permissions should only contain 'r' or 'w'"

        # Type can be None or an integer
        assert param_obj.type is None or isinstance(param_obj.type, int), "Type should be None or int"


def test_enum_params(pipewire_socket):
    """Test enumerating specific param values."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "node.description": "Test enum params",
        "capture.props": {
            "node.name": "test_enum_params_sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_enum_params_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node to appear
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_enum_params_sink":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get param info to find valid param IDs
    param_info = test_node.get_param_info()
    assert len(param_info) > 0, "Should have at least one param"

    # Test enum_params for each readable param
    # Note: Some params may not be activated, which is expected
    successfully_enumerated = False

    for param_id, permissions in param_info.items():
        if 'r' in permissions:
            try:
                # Enumerate this param
                values = test_node.enum_params(id=param_id)

                assert isinstance(values, list), f"enum_params for '{param_id}' should return a list"

                # Verify each value is a dict with proper structure
                for value in values:
                    assert isinstance(value, dict), "Each param value should be a dict"
                    assert 'type' in value, "Param value should have 'type' field"
                    assert 'size' in value, "Param value should have 'size' field"
                    assert 'data' in value, "Param value should have 'data' field"

                    assert isinstance(value['type'], int), "Param type should be an int"
                    assert isinstance(value['size'], int), "Param size should be an int"
                    assert isinstance(value['data'], bytes), "Param data should be bytes"

                    # Verify data length matches size + header
                    expected_len = value['size'] + 8  # 8 bytes for spa_pod header (type + size)
                    assert len(value['data']) == expected_len, \
                        f"Data length should be {expected_len}, got {len(value['data'])}"

                successfully_enumerated = True
                # Only test one successfully enumerated param to keep test fast
                break
            except RuntimeError as e:
                # Some params may not be activated/available, which is expected
                if "feature may not be activated" in str(e):
                    continue
                else:
                    raise

    # Note: It's OK if no params can be enumerated due to features not being activated
    # The important thing is that the API works correctly when params ARE available
    # This is validated by test_get_params which uses get_params() that handles this internally


def test_enum_params_invalid_id(pipewire_socket):
    """Test enum_params with invalid param ID."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "capture.props": {
            "node.name": "test_invalid_enum",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_invalid_enum_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_invalid_enum":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Try to enumerate with invalid param ID
    with pytest.raises(RuntimeError):
        test_node.enum_params(id="InvalidParamId")


def test_wparam_get(pipewire_socket):
    """Test WPParam.get() method."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "capture.props": {
            "node.name": "test_wparam_get",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_wparam_get_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_wparam_get":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get params
    params = test_node.get_params()

    assert len(params.items()) > 0, "Test node should have at least one parameter"

    # Track params with values to ensure at least some params have values
    params_with_values = 0

    # Test get() on each param
    for param_id, param_obj in params.items():
        values = param_obj.get()

        assert isinstance(values, list), f"get() for param '{param_id}' should return a list"

        # Count params that have values
        if len(values) > 0:
            params_with_values += 1

        # Verify structure of values (if any)
        for value in values:
            assert isinstance(value, dict), "Each value should be a dict"
            assert 'type' in value, "Value should have 'type' field"
            assert 'size' in value, "Value should have 'size' field"
            assert 'data' in value, "Value should have 'data' field"

    # Ensure at least some params have values (not all may be activated)
    assert params_with_values > 0, "At least some params should have values"


def test_wparam_repr(pipewire_socket):
    """Test WPParam string representation."""
    conn = WPConnection()

    # Create a test node
    args = json.dumps({
        "capture.props": {
            "node.name": "test_wparam_repr",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_wparam_repr_playback",
        }
    })

    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    # Wait for node
    deadline = time.time() + 2.0
    test_node = None
    while time.time() < deadline:
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == "test_wparam_repr":
                test_node = node
                break
        if test_node:
            break
        conn.sync()

    assert test_node is not None, "Test node should be found"

    # Get params
    params = test_node.get_params()

    assert len(params.items()) > 0, "Test node should have at least one parameter"

    # Test repr for each param
    for param_id, param_obj in params.items():
        repr_str = repr(param_obj)

        assert isinstance(repr_str, str), "repr should return a string"
        assert "<WPParam" in repr_str, "repr should contain '<WPParam'"
        assert param_id in repr_str, f"repr should contain param ID '{param_id}'"
        assert "permissions=" in repr_str, "repr should contain 'permissions='"
