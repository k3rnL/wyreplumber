from time import sleep

import json, time
from wyreplumber._core import WPConnection


def test_list_modules(pipewire_socket):
    """Test listing PipeWire modules."""
    conn = WPConnection()
    modules = conn.get_modules()

    # Validate the result
    assert isinstance(modules, list), "modules should be a list"


def test_load_module(pipewire_socket):
    conn = WPConnection()

    args = json.dumps({
        "node.description": "My loopback",
        "capture.props": {
            "node.name": "my_sink",
            "node.description": "My very first sink",
            "media.class": "Audio/Sink"
        },
        "playback.props": {
            "node.name": "my_sink_playback",
            "node.description": "My sink playback"
        }
    })

    # The module is loaded on the python's process, we do not expect get_modules to return it
    module = conn.load_module('libpipewire-module-loopback', arguments=args)

    assert module is not None, "Module should be loaded"

    # But we can check that the nodes were created
    deadline = time.time() + 2.0
    while time.time() < deadline:
        nodes = conn.get_nodes()
        names = {n.properties.get("node.name") for n in nodes}
        if {"my_sink", "my_sink_playback"} <= names:
            break
        conn.sync()  # important: pump + flush
    else:
        assert False, "nodes not created in time"


# def test_unload_module(pipewire_socket):
#     conn = WPConnection()
#
#     print([n.properties for n in conn.get_nodes()])
#
#     assert False
#
#     module = conn.load_module('libpipewire-module-loopback', arguments=args)
#     assert module is not None, "Module should be loaded"
#
#     conn.unload_module(module)
#     modules = conn.get_modules()
#     assert not any(module['name'] == 'test-module' for module in modules), "Module should be unloaded"
