import json
from dataclasses import FrozenInstanceError

import pytest

from wyreplumber.runtime import (
    Availability,
    ConnectionHealthValue,
    ConnectionState,
    DefaultsValue,
    DefaultTargetValue,
    DeviceValue,
    FrozenDict,
    LinkValue,
    MetadataEntryValue,
    MetadataValue,
    NodeState,
    NodeValue,
    ParameterValue,
    PortDirection,
    PortValue,
    ProfileValue,
    RouteValue,
    RuntimeSnapshot,
    RuntimeValueDecodeError,
    UnresolvedRelationshipValue,
    runtime_value_from_dict,
)


RUNTIME_VALUES = (
    ConnectionHealthValue(
        state=ConnectionState.CONNECTED,
        generation=7,
        details={"wireplumber_version": "0.5.8", "features": ["events", "params"]},
    ),
    DeviceValue(
        id=10,
        name="alsa_card.pci",
        description="Built-in audio",
        media_class="Audio/Device",
        properties={"device.api": "alsa", "api.alsa.card": 0},
        parameter_ids=("EnumProfile", "Profile", "EnumRoute", "Route"),
        profile_ids=(0, 1),
        route_ids=(0, 2),
    ),
    NodeValue(
        id=20,
        device_id=10,
        name="alsa_output.hdmi",
        description="HDMI output",
        media_class="Audio/Sink",
        state=NodeState.RUNNING,
        input_port_ids=(30, 31),
        properties={"audio.channels": 2, "audio.position": ["FL", "FR"]},
        parameter_ids=("Props", "Format"),
    ),
    PortValue(
        id=30,
        node_id=20,
        direction=PortDirection.INPUT,
        name="playback_FL",
        channel="FL",
        properties={"port.physical": True},
    ),
    LinkValue(
        id=40,
        output_node_id=21,
        output_port_id=32,
        input_node_id=20,
        input_port_id=30,
        state="active",
        owner="org.open-cinema",
        desired_id="tv-to-main-left",
        properties={"link.passive": False},
    ),
    MetadataEntryValue(
        subject=0,
        key="default.audio.sink",
        type_name="Spa:String:JSON",
        value='{"name":"alsa_output.hdmi"}',
    ),
    MetadataValue(
        id=50,
        name="default",
        properties={"metadata.name": "default"},
        entries=(
            MetadataEntryValue(
                subject=0,
                key="default.audio.sink",
                type_name="Spa:String:JSON",
                value='{"name":"alsa_output.hdmi"}',
            ),
        ),
    ),
    ParameterValue(
        owner_type="node",
        owner_id=20,
        id="Props",
        permissions="rw",
        values=(
            {"mute": False, "channelVolumes": [0.75, 0.75]},
            None,
        ),
        properties={"spa_type": "Props"},
    ),
    ProfileValue(
        device_id=10,
        index=1,
        name="output:hdmi-stereo",
        description="Digital Stereo (HDMI) Output",
        priority=5900,
        available=Availability.YES,
        active=True,
        properties={"classes": ["Audio/Sink"]},
    ),
    RouteValue(
        device_id=10,
        index=2,
        direction=PortDirection.OUTPUT,
        name="hdmi-output-0",
        description="HDMI / DisplayPort",
        priority=5900,
        available=Availability.YES,
        active=True,
        profile_ids=(1,),
        properties={"mute": False, "channelVolumes": [1.0, 1.0]},
    ),
    DefaultTargetValue(
        media_class="Audio/Sink",
        configured_name="alsa_output.hdmi",
        resolved_node_id=20,
    ),
    DefaultsValue(
        metadata_id=50,
        audio_sink=DefaultTargetValue(
            media_class="Audio/Sink",
            configured_name="alsa_output.hdmi",
            resolved_node_id=20,
        ),
        audio_source=DefaultTargetValue(
            media_class="Audio/Source",
            configured_name="alsa_input.spdif",
            resolved_node_id=22,
        ),
        extra={"default.video.source": {"name": "libcamera_input"}},
    ),
)


@pytest.mark.parametrize("value", RUNTIME_VALUES, ids=lambda value: value.VALUE_TYPE)
def test_runtime_value_round_trips_through_json(value):
    encoded = value.to_dict()

    assert encoded["schema_version"] == 1
    assert encoded["value_type"] == value.VALUE_TYPE

    decoded_json = json.loads(json.dumps(encoded, allow_nan=False))
    restored = runtime_value_from_dict(decoded_json)

    assert type(restored) is type(value)
    assert restored == value
    assert type(value).from_dict(decoded_json) == value


def test_runtime_values_are_deeply_immutable():
    value = ParameterValue(
        owner_type="node",
        owner_id=20,
        id="Props",
        permissions="rw",
        values=({"channelVolumes": [0.5, 0.75]},),
        properties={"labels": ["FL", "FR"]},
    )

    with pytest.raises(FrozenInstanceError):
        value.id = "Format"

    assert isinstance(value.values[0], FrozenDict)
    assert value.values[0]["channelVolumes"] == (0.5, 0.75)
    with pytest.raises(TypeError):
        value.values[0]["channelVolumes"] = (1.0, 1.0)
    with pytest.raises(TypeError):
        value.properties["labels"] = ("MONO",)
    with pytest.raises(TypeError, match="immutable"):
        value.properties._items = ()


def test_serialized_data_is_detached_from_the_value():
    value = DeviceValue(id=10, properties={"nested": {"enabled": True}})
    encoded = value.to_dict()

    encoded["properties"]["nested"]["enabled"] = False

    assert value.properties["nested"]["enabled"] is True


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    (
        ("schema_version", 2, "unsupported_schema_version"),
        ("value_type", "future_object", "unsupported_value_type"),
    ),
)
def test_decoder_rejects_unsupported_contract_values(field, replacement, code):
    encoded = DeviceValue(id=10).to_dict()
    encoded[field] = replacement

    with pytest.raises(RuntimeValueDecodeError) as error:
        runtime_value_from_dict(encoded)

    assert error.value.code == code


def test_decoder_rejects_unknown_fields_instead_of_discarding_them():
    encoded = DeviceValue(id=10).to_dict()
    encoded["future_field"] = "not silently ignored"

    with pytest.raises(RuntimeValueDecodeError) as error:
        runtime_value_from_dict(encoded)

    assert error.value.code == "unknown_fields"


def test_constructor_rejects_mutable_non_json_payloads():
    with pytest.raises(TypeError, match="not JSON-compatible"):
        ParameterValue(
            owner_type="node",
            owner_id=20,
            id="Props",
            permissions="rw",
            values=({"raw": b"native pod"},),
        )


def test_decoder_reports_wrong_concrete_type():
    encoded = NodeValue(id=20).to_dict()

    with pytest.raises(RuntimeValueDecodeError) as error:
        DeviceValue.from_dict(encoded)

    assert error.value.code == "unexpected_value_type"


def _complete_snapshot():
    return RuntimeSnapshot(
        generation=7,
        sequence=42,
        captured_at="2026-08-22T12:30:00+00:00",
        health=ConnectionHealthValue(
            state=ConnectionState.CONNECTED,
            generation=7,
        ),
        devices=(
            DeviceValue(
                id=10,
                name="alsa_card.pci",
                profile_ids=(1,),
                route_ids=(2,),
            ),
        ),
        nodes=(
            NodeValue(
                id=20,
                device_id=10,
                name="main-speakers",
                media_class="Audio/Sink",
                input_port_ids=(30,),
            ),
            NodeValue(
                id=21,
                name="tv-input",
                media_class="Audio/Source",
                output_port_ids=(32,),
            ),
        ),
        ports=(
            PortValue(id=30, node_id=20, direction=PortDirection.INPUT),
            PortValue(id=32, node_id=21, direction=PortDirection.OUTPUT),
        ),
        links=(
            LinkValue(
                id=40,
                output_node_id=21,
                output_port_id=32,
                input_node_id=20,
                input_port_id=30,
            ),
        ),
        metadata=(MetadataValue(id=50, name="default"),),
        parameters=(
            ParameterValue(
                owner_type="node",
                owner_id=20,
                id="Props",
                permissions="rw",
                values=({"mute": False},),
            ),
        ),
        profiles=(
            ProfileValue(
                device_id=10,
                index=1,
                name="output:analog-stereo",
                available=Availability.YES,
                active=True,
            ),
        ),
        routes=(
            RouteValue(
                device_id=10,
                index=2,
                direction=PortDirection.OUTPUT,
                name="analog-output-speaker",
                available=Availability.YES,
                active=True,
                profile_ids=(1,),
            ),
        ),
        defaults=DefaultsValue(
            metadata_id=50,
            audio_sink=DefaultTargetValue(
                media_class="Audio/Sink",
                configured_name="main-speakers",
                resolved_node_id=20,
            ),
        ),
    )


def test_runtime_snapshot_is_coherent_indexed_and_json_round_trippable():
    snapshot = _complete_snapshot()

    assert snapshot.captured_at == "2026-08-22T12:30:00Z"
    assert snapshot.is_coherent
    assert snapshot.unresolved_relationships == ()
    assert snapshot.nodes_by_id[20].name == "main-speakers"
    assert snapshot.parameters_by_key[("node", 20, "Props")].permissions == "rw"
    assert snapshot.profiles_by_key[(10, 1)].active
    assert snapshot.routes_by_key[(10, 2)].name == "analog-output-speaker"

    with pytest.raises(TypeError):
        snapshot.nodes_by_id[99] = NodeValue(id=99)

    encoded = json.loads(json.dumps(snapshot.to_dict(), allow_nan=False))
    assert "nodes_by_id" not in encoded
    restored = RuntimeSnapshot.from_dict(encoded)

    assert restored == snapshot
    assert restored.nodes_by_id[20] == snapshot.nodes_by_id[20]


def test_runtime_snapshot_reports_absent_relationship_targets():
    snapshot = RuntimeSnapshot(
        generation=8,
        sequence=1,
        captured_at="2026-08-22T12:30:00Z",
        health=ConnectionHealthValue(
            state=ConnectionState.DEGRADED,
            generation=8,
        ),
        nodes=(NodeValue(id=20, device_id=999, input_port_ids=(30,)),),
        defaults=DefaultsValue(
            audio_sink=DefaultTargetValue(
                media_class="Audio/Sink",
                resolved_node_id=888,
            )
        ),
    )

    assert not snapshot.is_coherent
    assert {
        (item.source_type, item.relation, item.target_type, item.target_id)
        for item in snapshot.unresolved_relationships
    } == {
        ("node", "device", "device", 999),
        ("node", "input_port", "port", 30),
        ("defaults", "resolved_node", "node", 888),
    }


def test_runtime_snapshot_rejects_mixed_generation_health():
    with pytest.raises(ValueError, match="generation"):
        RuntimeSnapshot(
            generation=8,
            sequence=1,
            captured_at="2026-08-22T12:30:00Z",
            health=ConnectionHealthValue(
                state=ConnectionState.CONNECTED,
                generation=7,
            ),
        )


def test_runtime_snapshot_rejects_duplicate_object_identity():
    with pytest.raises(ValueError, match="duplicate node id"):
        RuntimeSnapshot(
            generation=7,
            sequence=1,
            captured_at="2026-08-22T12:30:00Z",
            health=ConnectionHealthValue(
                state=ConnectionState.CONNECTED,
                generation=7,
            ),
            nodes=(NodeValue(id=20), NodeValue(id=20)),
        )


def test_runtime_snapshot_rejects_tampered_relationship_validation():
    encoded = _complete_snapshot().to_dict()
    encoded["unresolved_relationships"] = [
        UnresolvedRelationshipValue(
            source_type="node",
            source_id=20,
            relation="device",
            target_type="device",
            target_id=999,
            reason="fabricated",
        ).to_dict()
    ]

    with pytest.raises(RuntimeValueDecodeError, match="do not match"):
        RuntimeSnapshot.from_dict(encoded)
