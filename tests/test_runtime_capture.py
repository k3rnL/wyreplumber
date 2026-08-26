from datetime import datetime

from wyreplumber._core import WPConnection, WPPipewireObject


EXPECTED_PAYLOAD_KEYS = {
    "payload_version",
    "generation",
    "sequence",
    "captured_at",
    "health",
    "devices",
    "nodes",
    "ports",
    "links",
    "metadata",
    "parameters",
    "profiles",
    "routes",
    "defaults",
}


def _assert_primitive(value):
    assert not isinstance(value, WPPipewireObject)
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _assert_primitive(item)
    elif isinstance(value, list):
        for item in value:
            _assert_primitive(item)
    else:
        assert value is None or isinstance(value, (bool, int, float, str, bytes))


def test_capture_runtime_payload_is_detached_and_monotonic(pipewire_socket):
    connection = WPConnection()

    first = connection.capture_runtime_payload()
    second = connection.capture_runtime_payload()

    assert set(first) == EXPECTED_PAYLOAD_KEYS
    assert first["payload_version"] == 1
    assert first["generation"] >= 1
    assert second["generation"] == first["generation"]
    assert second["sequence"] == first["sequence"] + 1
    assert datetime.fromisoformat(first["captured_at"].replace("Z", "+00:00")).tzinfo
    assert first["health"]["state"] == "connected"
    assert first["health"]["generation"] == first["generation"]
    assert first["health"]["details"]["wireplumber_api_version"]
    assert first["health"]["details"]["pipewire_remote_version"]

    for collection in (
        "devices",
        "nodes",
        "ports",
        "links",
        "metadata",
        "parameters",
        "profiles",
        "routes",
        "defaults",
    ):
        assert isinstance(first[collection], list)

    _assert_primitive(first)


def test_parameter_profile_route_and_default_payload_shapes(pipewire_socket):
    payload = WPConnection().capture_runtime_payload()

    for parameter in payload["parameters"]:
        assert {
            "owner_type",
            "owner_id",
            "id",
            "permissions",
            "complete",
            "values",
        } <= set(parameter)
        assert parameter["owner_type"] in {"device", "node", "port", "link"}
        assert isinstance(parameter["values"], list)

    assert all(item["id"] in {"Profile", "EnumProfile"} for item in payload["profiles"])
    assert all(item["id"] in {"Route", "EnumRoute"} for item in payload["routes"])
    assert all(item["key"].startswith("default.") for item in payload["defaults"])
