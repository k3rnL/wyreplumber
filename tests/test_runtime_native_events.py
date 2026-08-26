import json
from time import monotonic

import pytest

from wyreplumber._core import WPConnection, WPPipewireObject
from wyreplumber.runtime import (
    NodeValue,
    RuntimeEventKind,
    RuntimeObjectKind,
    RuntimePayloadError,
    capture_runtime_snapshot,
    next_runtime_event,
    runtime_event_from_payload,
)


def _node_event_payload():
    return {
        "payload_version": 1,
        "generation": 3,
        "sequence": 6,
        "occurred_at": "2026-08-22T16:00:00Z",
        "kind": "object_added",
        "object_kind": "node",
        "object_id": 20,
        "current": {
            "id": 20,
            "properties": {
                "node.name": "main-speakers",
                "media.class": "Audio/Sink",
            },
            "parameter_ids": ["Props"],
            "state": 2,
            "error": None,
        },
        "previous": None,
        "requires_resnapshot": False,
        "reason": None,
    }


def _assert_detached(value):
    assert not isinstance(value, WPPipewireObject)
    if isinstance(value, dict):
        for item in value.values():
            _assert_detached(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_detached(item)


def test_native_event_payload_builds_a_typed_serializable_event():
    event = runtime_event_from_payload(_node_event_payload())

    assert event.kind is RuntimeEventKind.OBJECT_ADDED
    assert event.object_kind is RuntimeObjectKind.NODE
    assert isinstance(event.current, NodeValue)
    assert event.current.name == "main-speakers"
    json.dumps(event.to_dict(), allow_nan=False)


def test_native_event_payload_validation_is_structured():
    payload = _node_event_payload()
    payload["payload_version"] = 2

    with pytest.raises(RuntimePayloadError) as error:
        runtime_event_from_payload(payload)

    assert error.value.code == "unsupported_event_payload_version"


def test_failed_parameter_event_fallback_encodes_raw_pod_bytes():
    payload = _node_event_payload()
    payload.update(
        kind="parameter_changed",
        object_kind="parameter",
        object_id="device:157:Profile",
        current={
            "owner_type": "device",
            "owner_id": 157,
            "id": "Profile",
            "permissions": "r",
            "complete": True,
            "values": [{"unsupported": b"\x00\xff"}],
        },
    )

    event = runtime_event_from_payload(payload)
    encoded = event.to_dict()

    assert encoded["current"]["values"][0]["unsupported"] == {
        "encoding": "base64",
        "data": "AP8=",
    }
    json.dumps(encoded, allow_nan=False)


def test_registry_signals_publish_ordered_detached_events(pipewire_socket):
    connection = WPConnection(event_capacity=128)
    snapshot = capture_runtime_snapshot(connection)
    assert connection.drain_runtime_event_payloads() == []

    arguments = json.dumps(
        {
            "node.description": "Runtime event loopback",
            "capture.props": {
                "node.name": "runtime_event_sink",
                "media.class": "Audio/Sink",
            },
            "playback.props": {
                "node.name": "runtime_event_playback",
            },
        }
    )
    module = connection.load_module(
        "libpipewire-module-loopback",
        arguments=arguments,
    )

    sequences = []
    observed = None
    deadline = monotonic() + 4
    while monotonic() < deadline:
        event = next_runtime_event(
            connection,
            timeout=max(0, deadline - monotonic()),
        )
        if event is None:
            continue
        sequences.append(event.sequence)
        _assert_detached(event.to_dict())
        if (
            event.kind is RuntimeEventKind.OBJECT_ADDED
            and event.object_kind is RuntimeObjectKind.NODE
            and isinstance(event.current, NodeValue)
            and event.current.name == "runtime_event_sink"
        ):
            observed = event
            break

    assert module is not None
    assert observed is not None
    assert observed.generation == snapshot.generation
    assert sequences == list(range(snapshot.sequence + 1, sequences[-1] + 1))

    removal_baseline = capture_runtime_snapshot(connection)
    target = next(
        node
        for node in connection.get_nodes()
        if node.properties.get("node.name") == "runtime_event_sink"
    )
    target_id = target.id
    target.delete()

    removed = None
    removal_sequences = []
    deadline = monotonic() + 4
    while monotonic() < deadline:
        event = next_runtime_event(
            connection,
            timeout=max(0, deadline - monotonic()),
        )
        if event is None:
            continue
        removal_sequences.append(event.sequence)
        if (
            event.kind is RuntimeEventKind.OBJECT_REMOVED
            and event.object_kind is RuntimeObjectKind.NODE
            and event.object_id == target_id
        ):
            removed = event
            break

    assert removed is not None
    assert removal_sequences == list(
        range(removal_baseline.sequence + 1, removal_sequences[-1] + 1)
    )


def test_connection_signal_is_published_without_a_python_callback(pipewire_socket):
    connection = WPConnection()

    event = next_runtime_event(connection, timeout=1)

    assert event is not None
    assert event.kind is RuntimeEventKind.CONNECTION_CHANGED
    assert event.object_kind is RuntimeObjectKind.CONNECTION
    assert event.current.state.value == "connected"


def test_native_queue_overflow_is_one_explicit_discontinuity(pipewire_socket):
    connection = WPConnection(event_capacity=1)
    snapshot = capture_runtime_snapshot(connection)
    arguments = json.dumps(
        {
            "capture.props": {
                "node.name": "runtime_overflow_sink",
                "media.class": "Audio/Sink",
            },
            "playback.props": {"node.name": "runtime_overflow_playback"},
        }
    )
    module = connection.load_module(
        "libpipewire-module-loopback",
        arguments=arguments,
    )
    deadline = monotonic() + 4
    while monotonic() < deadline:
        names = {node.properties.get("node.name") for node in connection.get_nodes()}
        if "runtime_overflow_sink" in names:
            break
        connection.sync()
    else:
        pytest.fail("controlled loopback node did not appear")

    payloads = connection.drain_runtime_event_payloads()
    events = tuple(runtime_event_from_payload(payload) for payload in payloads)

    assert module is not None
    assert len(events) == 1
    assert events[0].generation == snapshot.generation
    assert events[0].kind is RuntimeEventKind.DISCONTINUITY
    assert events[0].requires_resnapshot
    assert events[0].reason == "native event queue capacity 1 exceeded"
