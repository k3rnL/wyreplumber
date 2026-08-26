import json
from pathlib import Path

import pytest

from wyreplumber.runtime import (
    AudioFormatValue,
    AudioPropertiesValue,
    Availability,
    ParameterValue,
    PortDirection,
    ProfileValue,
    RouteValue,
    SpaChoiceValue,
    normalize_spa_json,
    normalize_spa_parameter,
)
from wyreplumber.spa_pod import (
    SpaAudioChannel,
    SpaAudioFormat,
    SpaFormat,
    SpaMediaSubtype,
    SpaMediaType,
    SpaProps,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "wireplumber-0.5"


def _fixture(name):
    with (FIXTURE_DIRECTORY / f"{name}.json").open() as fixture_file:
        return json.load(fixture_file)


def _normalize_fixture(name):
    fixture = _fixture(name)
    assert fixture["wireplumber_family"] == "0.5"
    assert fixture["representation"] == "parsed-spa"
    return normalize_spa_parameter(
        owner_type=fixture["owner_type"],
        owner_id=fixture["owner_id"],
        parameter_id=fixture["parameter_id"],
        permissions=fixture["permissions"],
        values=fixture["values"],
    )


@pytest.mark.parametrize("name", ("props", "format", "profile", "route"))
def test_wireplumber_0_5_fixtures_normalize_and_round_trip(name):
    parameter = _normalize_fixture(name)

    encoded = json.loads(json.dumps(parameter.to_dict(), allow_nan=False))

    assert ParameterValue.from_dict(encoded) == parameter


def test_props_normalization_is_typed_and_preserves_unknown_fields():
    parameter = _normalize_fixture("props")
    props = parameter.values[0]

    assert isinstance(props, AudioPropertiesValue)
    assert props.volume == 0.8
    assert props.mute is False
    assert props.channel_volumes == (0.75, 0.8)
    assert [position.name for position in props.channel_positions] == ["FL", "FR"]
    assert props.extra["vendor.future"]["enabled"] is True


def test_format_normalization_types_choices_rates_channels_and_positions():
    parameter = _normalize_fixture("format")
    audio_format = parameter.values[0]

    assert isinstance(audio_format, AudioFormatValue)
    assert audio_format.media_type.name == "AUDIO"
    assert audio_format.media_subtype.name == "RAW"
    assert isinstance(audio_format.sample_format, SpaChoiceValue)
    assert audio_format.sample_format.kind == "enum"
    assert audio_format.sample_format.flags == 1
    assert audio_format.sample_format.default.name == "S16_LE"
    assert [value.name for value in audio_format.sample_format.alternatives] == ["F32_LE"]
    assert isinstance(audio_format.rate, SpaChoiceValue)
    assert audio_format.rate.default == 48000
    assert audio_format.rate.minimum == 32000
    assert audio_format.rate.maximum == 192000
    assert audio_format.channels == 2
    assert [position.name for position in audio_format.positions] == ["FL", "FR"]
    assert audio_format.extra["future.format.flag"] == 17


def test_profile_and_route_normalization_uses_runtime_value_types():
    profile = _normalize_fixture("profile").values[0]
    route = _normalize_fixture("route").values[0]

    assert isinstance(profile, ProfileValue)
    assert profile.device_id == 10
    assert profile.index == 1
    assert profile.available is Availability.YES
    assert profile.classes == ("Audio/Sink",)
    assert profile.properties["info"]["device.profile.name"] == "hdmi-stereo"

    assert isinstance(route, RouteValue)
    assert route.device_id == 10
    assert route.index == 2
    assert route.direction is PortDirection.OUTPUT
    assert route.available is Availability.YES
    assert route.profile_ids == (1,)
    assert route.volume == 0.9
    assert route.mute is False
    assert route.channel_volumes == (0.9, 0.9)
    assert [position.name for position in route.channel_positions] == ["FL", "FR"]
    assert route.properties["spa_device_index"] == 0
    assert route.properties["future.route.field"]["mode"] == "auto"
    assert route.properties["audio_extra"]["api.alsa.extra"] == "preserved"


def test_normalizer_accepts_typed_spa_objects_without_mutating_them():
    raw_props = SpaProps(
        volume=0.5,
        mute=True,
        channelVolumes=[0.4, 0.5],
        channelMap=[SpaAudioChannel.FL, SpaAudioChannel.FR],
        vendorExtension={"enabled": True},
    )
    raw_format = SpaFormat(
        mediaType=SpaMediaType.AUDIO,
        mediaSubtype=SpaMediaSubtype.RAW,
        audio_format=SpaAudioFormat.F32_LE,
        audio_rate=48000,
        audio_channels=2,
        audio_position=[SpaAudioChannel.FL, SpaAudioChannel.FR],
    )

    props_parameter = normalize_spa_parameter(
        owner_type="node",
        owner_id=20,
        parameter_id="Props",
        permissions="rw",
        values=(raw_props,),
    )
    format_parameter = normalize_spa_parameter(
        owner_type="node",
        owner_id=20,
        parameter_id="Format",
        permissions="r",
        values=(raw_format,),
    )

    assert props_parameter.values[0].mute is True
    assert props_parameter.values[0].extra["vendorExtension"]["enabled"] is True
    assert format_parameter.values[0].sample_format.name == "F32_LE"
    assert raw_props.volume == 0.5
    assert raw_format.audio_rate == 48000


def test_unknown_spa_values_remain_json_compatible():
    normalized = normalize_spa_json(
        {
            "future": b"\x00\x01\xff",
            "channel": SpaAudioChannel.FC,
        }
    )

    assert normalized == {
        "future": {"encoding": "base64", "data": "AAH/"},
        "channel": {"id": 5, "name": "FC", "namespace": "SpaAudioChannel"},
    }
    json.dumps(normalized, allow_nan=False)


def test_profile_normalization_accepts_unspecialized_native_class_struct():
    parameter = normalize_spa_parameter(
        owner_type="device",
        owner_id=157,
        parameter_id="Profile",
        permissions="rw",
        values=(
            {
                "index": 2,
                "name": "a2dp-sink",
                "classes": {
                    "_pod_type": 14,
                    "values": [
                        {
                            "_pod_type": 14,
                            "values": [
                                "Audio/Sink",
                                1,
                                "card.profile.devices",
                                {
                                    "_pod_type": 13,
                                    "child_size": 4,
                                    "child_type": 4,
                                    "values": [1],
                                },
                            ],
                        }
                    ],
                },
            },
        ),
    )

    assert parameter.values[0].classes == ("Audio/Sink",)
