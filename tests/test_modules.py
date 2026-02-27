import json
import time
import pytest

from wyreplumber._core import (
    WPConnection,
    WPModule,
)


def test_list_modules(pipewire_socket):
    """Test listing PipeWire modules."""
    conn = WPConnection()
    modules = conn.get_modules()

    # Validate the result
    assert isinstance(modules, list), "modules should be a list"


def test_load_module(pipewire_socket):
    """Test loading a module and verifying nodes are created."""
    conn = WPConnection()

    args = json.dumps({
        "node.description": "My loopback",
        "capture.props": {
            "node.name": "test_my_sink",
            "node.description": "My very first sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "test_my_sink_playback",
            "node.description": "My sink playback"
        }
    })

    # The module is loaded on the python's process, we do not expect get_modules to return it
    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    assert module is not None, "Module should be loaded"
    assert isinstance(module, WPModule), "Module should be a WPModule instance"
    assert module.name == "libpipewire-module-loopback", "Module name should match"
    assert module.arguments == args, "Module arguments should match"
    assert isinstance(module.properties, dict), "Module properties should be a dict"

    # But we can check that the nodes were created
    deadline = time.time() + 2.0
    while time.time() < deadline:
        nodes = conn.get_nodes()
        names = {n.properties.get("node.name") for n in nodes}
        if {"test_my_sink", "test_my_sink_playback"} <= names:
            break
        conn.sync()  # important: pump + flush
    else:
        assert False, "nodes not created in time"