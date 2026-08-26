import copy
import struct

import pytest

from wyreplumber._core import WPConnection, WPPipewireObject
from wyreplumber.runtime import (
    AudioPropertiesValue,
    PortDirection,
    RuntimePayloadError,
    capture_runtime_snapshot,
    runtime_snapshot_from_payload,
)
from wyreplumber.spa_pod import (
    SpaAudioChannel,
    SpaParamAvailability,
    SpaParamProfile,
    SpaParamRoute,
    SpaProps,
    build_spa_pod,
)


def _raw_pod(value):
    data = build_spa_pod(value)
    size, pod_type = struct.unpack_from("<II", data)
    return {"type": pod_type, "size": size, "data": data}


def _parameter(owner_type, owner_id, parameter_id, value):
    return {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "id": parameter_id,
        "permissions": "rw",
        "complete": True,
        "values": [_raw_pod(value)],
    }


def _payload():
    profile = _parameter(
        "device",
        10,
        "EnumProfile",
        SpaParamProfile(
            index=1,
            name="output:analog-stereo",
            description="Analog Stereo Output",
            priority=100,
            available=SpaParamAvailability.YES,
            classes=["Audio/Sink"],
        ),
    )
    route = _parameter(
        "device",
        10,
        "EnumRoute",
        SpaParamRoute(
            index=2,
            direction=1,
            device=0,
            name="analog-output-speaker",
            description="Speakers",
            priority=100,
            available=SpaParamAvailability.YES,
            profiles=[1],
            props=SpaProps(
                volume=0.8,
                mute=False,
                channelVolumes=[0.8, 0.8],
                channelMap=[SpaAudioChannel.FL, SpaAudioChannel.FR],
            ),
        ),
    )
    props = _parameter(
        "node",
        20,
        "Props",
        SpaProps(
            volume=0.75,
            mute=False,
            channelVolumes=[0.75, 0.75],
            channelMap=[SpaAudioChannel.FL, SpaAudioChannel.FR],
        ),
    )
    return {
        "payload_version": 1,
        "generation": 3,
        "sequence": 5,
        "captured_at": "2026-08-22T12:30:00Z",
        "health": {
            "state": "connected",
            "generation": 3,
            "reason": None,
            "details": {"wireplumber_api_version": "0.5"},
        },
        "devices": [
            {
                "id": 10,
                "properties": {
                    "device.name": "alsa_card.pci",
                    "device.description": "Built-in audio",
                    "media.class": "Audio/Device",
                },
                "parameter_ids": ["EnumProfile", "EnumRoute"],
            }
        ],
        "nodes": [
            {
                "id": 20,
                "properties": {
                    "device.id": "10",
                    "node.name": "main-speakers",
                    "node.description": "Main speakers",
                    "media.class": "Audio/Sink",
                },
                "parameter_ids": ["Props"],
                "state": 3,
                "error": None,
            },
            {
                "id": 21,
                "properties": {
                    "node.name": "tv-input",
                    "media.class": "Audio/Source",
                },
                "parameter_ids": [],
                "state": 2,
                "error": None,
            },
        ],
        "ports": [
            {
                "id": 30,
                "properties": {
                    "node.id": "20",
                    "port.name": "playback_FL",
                    "audio.channel": "FL",
                },
                "parameter_ids": [],
                "direction": 0,
            },
            {
                "id": 32,
                "properties": {
                    "node.id": "21",
                    "port.name": "capture_FL",
                    "audio.channel": "FL",
                },
                "parameter_ids": [],
                "direction": 1,
            },
        ],
        "links": [
            {
                "id": 40,
                "properties": {"link.passive": "false"},
                "parameter_ids": [],
                "output_node_id": 21,
                "output_port_id": 32,
                "input_node_id": 20,
                "input_port_id": 30,
                "state": 4,
                "error": None,
            }
        ],
        "metadata": [
            {
                "id": 50,
                "name": "default",
                "properties": {"metadata.name": "default"},
                "entries": [
                    {
                        "subject": 0,
                        "key": "default.audio.sink",
                        "type": "Spa:String:JSON",
                        "value": '{"name":"main-speakers"}',
                    }
                ],
            }
        ],
        "parameters": [profile, route, props],
        "profiles": [profile],
        "routes": [route],
        "defaults": [
            {
                "metadata_id": 50,
                "metadata_name": "default",
                "subject": 0,
                "key": "default.audio.sink",
                "type": "Spa:String:JSON",
                "value": '{"name":"main-speakers"}',
            }
        ],
    }


def test_native_payload_builds_a_coherent_detached_snapshot():
    snapshot = runtime_snapshot_from_payload(_payload())

    assert snapshot.generation == 3
    assert snapshot.sequence == 5
    assert snapshot.is_coherent
    assert snapshot.devices_by_id[10].profile_ids == (1,)
    assert snapshot.devices_by_id[10].route_ids == (2,)
    assert snapshot.nodes_by_id[20].input_port_ids == (30,)
    assert snapshot.nodes_by_id[21].output_port_ids == (32,)
    assert snapshot.ports_by_id[30].direction is PortDirection.INPUT
    assert snapshot.links_by_id[40].state == "active"
    assert snapshot.defaults.audio_sink.resolved_node_id == 20
    assert snapshot.defaults.metadata_id == 50
    assert isinstance(snapshot.parameters_by_key[("node", 20, "Props")].values[0], AudioPropertiesValue)


def test_disappearing_object_does_not_invalidate_an_older_snapshot():
    first = runtime_snapshot_from_payload(_payload())
    changed_payload = copy.deepcopy(_payload())
    changed_payload["sequence"] = 6
    changed_payload["nodes"] = [
        node for node in changed_payload["nodes"] if node["id"] != 21
    ]

    second = runtime_snapshot_from_payload(changed_payload)

    assert first.nodes_by_id[21].name == "tv-input"
    assert 21 not in second.nodes_by_id
    assert not second.is_coherent
    assert any(
        item.target_type == "node" and item.target_id == 21
        for item in second.unresolved_relationships
    )


def test_payload_rejects_a_native_or_application_object():
    payload = _payload()
    payload["health"]["details"]["leaked"] = object()

    with pytest.raises(RuntimePayloadError) as error:
        runtime_snapshot_from_payload(payload)

    assert error.value.code == "native_object_leak"
    assert error.value.path == "$.health.details.leaked"


def test_native_connection_captures_runtime_snapshot(pipewire_socket):
    connection = WPConnection()

    first = capture_runtime_snapshot(connection)
    second = capture_runtime_snapshot(connection)

    assert second.generation == first.generation
    assert second.sequence == first.sequence + 1
    for collection in (
        first.devices,
        first.nodes,
        first.ports,
        first.links,
        first.metadata,
        first.parameters,
    ):
        assert not any(isinstance(value, WPPipewireObject) for value in collection)
