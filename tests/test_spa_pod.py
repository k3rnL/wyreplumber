import math

import pytest

from wyreplumber import spa_pod


@pytest.mark.parametrize(
    ("value", "pod_type", "expected"),
    [
        (None, spa_pod.SPA_TYPE_None, None),
        (True, spa_pod.SPA_TYPE_Bool, True),
        (42, spa_pod.SPA_TYPE_Id, 42),
        (-7, spa_pod.SPA_TYPE_Int, -7),
        (2**40, spa_pod.SPA_TYPE_Long, 2**40),
        (3.5, spa_pod.SPA_TYPE_Float, 3.5),
        (9.25, spa_pod.SPA_TYPE_Double, 9.25),
        ("hello", spa_pod.SPA_TYPE_String, "hello"),
        (b"\x01\x02", spa_pod.SPA_TYPE_Bytes, b"\x01\x02"),
        ({"width": 640, "height": 480}, spa_pod.SPA_TYPE_Rectangle, {"_pod_type": spa_pod.SPA_TYPE_Rectangle, "width": 640, "height": 480}),
        ({"num": 30000, "denom": 1001}, spa_pod.SPA_TYPE_Fraction, {"_pod_type": spa_pod.SPA_TYPE_Fraction, "num": 30000, "denom": 1001}),
        ({"data": b"\xaa\xbb"}, spa_pod.SPA_TYPE_Bitmap, {"_pod_type": spa_pod.SPA_TYPE_Bitmap, "data": b"\xaa\xbb"}),
        (11, spa_pod.SPA_TYPE_Fd, 11),
    ],
)
def test_scalar_roundtrip(value, pod_type, expected):
    pod = spa_pod.build_spa_pod(value, pod_type)
    parsed = spa_pod.parse_spa_pod(pod)

    if isinstance(expected, float):
        assert math.isclose(parsed, expected, rel_tol=1e-6)
    else:
        assert parsed == expected


def test_array_choice_sequence_roundtrip():
    array_value = {
        "_pod_type": spa_pod.SPA_TYPE_Array,
        "child_type": spa_pod.SPA_TYPE_Int,
        "values": [1, 2, 3, 4],
    }
    choice_value = {
        "_pod_type": spa_pod.SPA_TYPE_Choice,
        "choice_type": spa_pod.SPA_CHOICE_Range,
        "child_type": spa_pod.SPA_TYPE_Int,
        "values": [128, 64, 512],
    }
    sequence_value = {
        "_pod_type": spa_pod.SPA_TYPE_Sequence,
        "unit": 7,
        "controls": [
            {"offset": 0, "type": spa_pod.SPA_CONTROL_Properties, "value": 33},
            {"offset": 64, "type": spa_pod.SPA_CONTROL_Midi, "value": b"\x90\x3c\x7f"},
        ],
    }

    parsed_array = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(array_value))
    parsed_choice = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(choice_value))
    parsed_sequence = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(sequence_value))

    assert parsed_array == {"_pod_type": spa_pod.SPA_TYPE_Array, "child_size": 4, "child_type": spa_pod.SPA_TYPE_Int, "values": [1, 2, 3, 4]}
    assert parsed_choice["default"] == 128
    assert parsed_choice["min"] == 64
    assert parsed_choice["max"] == 512
    assert parsed_sequence["unit"] == 7
    assert parsed_sequence["controls"][0]["value"] == 33
    assert parsed_sequence["controls"][1]["value"] == b"\x90\x3c\x7f"


def test_pointer_and_embedded_pod_roundtrip():
    pointer_value = {
        "_pod_type": spa_pod.SPA_TYPE_Pointer,
        "pointer_type": spa_pod.SPA_TYPE_POINTER_Buffer,
        "value": 0x1234_5678,
    }
    embedded_value = {
        "_pod_type": spa_pod.SPA_TYPE_Pod,
        "pod": {
            "_pod_type": spa_pod.SPA_TYPE_Choice,
            "choice_type": spa_pod.SPA_CHOICE_Enum,
            "child_type": spa_pod.SPA_TYPE_Id,
            "values": [1, 2, 3],
        },
    }

    parsed_pointer = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(pointer_value))
    parsed_embedded = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(embedded_value))

    assert parsed_pointer == pointer_value
    assert parsed_embedded["pod"]["alternatives"] == [2, 3]


def test_props_object_specialization_roundtrip():
    value = spa_pod.SpaProps(
        mute=True,
        volume=0.75,
        channelMap=[1, 2],
        params={"api.alsa.path": "hw:0", "session.suspend-timeout-seconds": 5},
    )

    parsed = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(value))

    assert isinstance(parsed, spa_pod.SpaProps)
    assert parsed.object_name == "Props"
    assert parsed.mute is True
    assert parsed["mute"] is True
    assert parsed[spa_pod.SPA_PROP_mute] is True
    assert math.isclose(parsed.volume, 0.75, rel_tol=1e-6)
    assert math.isclose(parsed["volume"], 0.75, rel_tol=1e-6)
    assert math.isclose(parsed[spa_pod.SPA_PROP_volume], 0.75, rel_tol=1e-6)
    assert parsed.channelMap == [1, 2]
    assert parsed.params == {
        "api.alsa.path": "hw:0",
        "session.suspend-timeout-seconds": 5,
    }
    assert parsed.property_keys["mute"] == spa_pod.SPA_PROP_mute
    parsed[spa_pod.SPA_PROP_volume] = 0.25
    assert math.isclose(parsed.volume, 0.25, rel_tol=1e-6)
    parsed.mute = False
    assert parsed["mute"] is False


def test_route_and_format_specialization_roundtrip():
    value = spa_pod.SpaParamRoute(
        index=2,
        direction=spa_pod.SPA_DIRECTION_OUTPUT,
        name="speaker",
        profiles=[3, 5],
        info={"device.icon-name": "audio-speakers"},
        props=spa_pod.SpaProps(mute=False, volume=0.5),
    )

    parsed = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(value))
    nested_props = parsed.props

    assert isinstance(parsed, spa_pod.SpaParamRoute)
    assert parsed.profiles == [3, 5]
    assert parsed.info == {"device.icon-name": "audio-speakers"}
    assert isinstance(nested_props, spa_pod.SpaProps)
    assert nested_props.object_id == spa_pod.SPA_PARAM_Props
    assert nested_props.mute is False
    assert math.isclose(nested_props.volume, 0.5, rel_tol=1e-6)

    format_value = spa_pod.SpaFormat(
        mediaType=spa_pod.SpaMediaType.AUDIO,
        mediaSubtype=spa_pod.SpaMediaSubtype.RAW,
        audio_format=spa_pod.SpaAudioFormat.S16_BE,
        audio_rate=48000,
        audio_channels=2,
        audio_position=[spa_pod.SpaAudioChannel.FL, spa_pod.SpaAudioChannel.FR],
        audio_bitorder=spa_pod.SpaParamBitorder.MSB,
    )

    parsed_format = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(format_value))
    assert isinstance(parsed_format, spa_pod.SpaFormat)
    assert parsed_format.mediaType is spa_pod.SpaMediaType.AUDIO
    assert parsed_format.mediaSubtype is spa_pod.SpaMediaSubtype.RAW
    assert parsed_format.audio_format is spa_pod.SpaAudioFormat.S16_BE
    assert parsed_format.audio_rate == 48000
    assert parsed_format.audio_position == [spa_pod.SpaAudioChannel.FL, spa_pod.SpaAudioChannel.FR]
    assert parsed_format.audio_bitorder is spa_pod.SpaParamBitorder.MSB


def test_spa_pod_enum_properties_and_choices_roundtrip():
    props_value = spa_pod.SpaProps(
        bluetoothAudioCodec=spa_pod.SpaBluetoothAudioCodec.LDAC,
        channelMap=[spa_pod.SpaAudioChannel.FL, spa_pod.SpaAudioChannel.FR],
        iec958Codecs=[spa_pod.SpaAudioIec958Codec.PCM],
        volumeRampScale=spa_pod.SpaAudioVolumeRampScale.LINEAR,
    )

    parsed_props = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(props_value))
    assert parsed_props.bluetoothAudioCodec is spa_pod.SpaBluetoothAudioCodec.LDAC
    assert parsed_props.channelMap == [spa_pod.SpaAudioChannel.FL, spa_pod.SpaAudioChannel.FR]
    assert parsed_props.iec958Codecs == [spa_pod.SpaAudioIec958Codec.PCM]
    assert parsed_props.volumeRampScale is spa_pod.SpaAudioVolumeRampScale.LINEAR

    enum_format = spa_pod.SpaFormat(
        mediaType=spa_pod.SpaMediaType.AUDIO,
        mediaSubtype=spa_pod.SpaMediaSubtype.RAW,
        audio_format={
            "_pod_type": spa_pod.SPA_TYPE_Choice,
            "choice_type": spa_pod.SPA_CHOICE_Enum,
            "values": [
                spa_pod.SpaAudioFormat.F32_LE,
                spa_pod.SpaAudioFormat.S16_LE,
            ],
        },
    )

    parsed_enum_format = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(enum_format))
    assert parsed_enum_format.audio_format["child_type"] == spa_pod.SPA_TYPE_Id
    assert parsed_enum_format.audio_format["default"] is spa_pod.SpaAudioFormat.F32_LE
    assert parsed_enum_format.audio_format["alternatives"] == [spa_pod.SpaAudioFormat.S16_LE]
    assert parsed_enum_format.audio_format["values"] == [
        spa_pod.SpaAudioFormat.F32_LE,
        spa_pod.SpaAudioFormat.S16_LE,
    ]


def test_profile_classes_and_dict_helpers():
    profile_value = spa_pod.SpaParamProfile(
        index=1,
        name="analog-stereo",
        info={"device.api": "alsa", "card.profile.device": "0"},
        classes=[
            {
                "class": "Audio/Source",
                "count": 1,
                "property": "device.profile.description",
                "devices": [0, 1],
            }
        ],
        save=True,
    )

    parsed_profile = spa_pod.parse_spa_pod(spa_pod.build_spa_pod(profile_value))
    assert isinstance(parsed_profile, spa_pod.SpaParamProfile)
    assert parsed_profile.info == {
        "device.api": "alsa",
        "card.profile.device": "0",
    }
    assert parsed_profile.classes == [
        {
            "class": "Audio/Source",
            "count": 1,
            "property": "device.profile.description",
            "devices": [0, 1],
        }
    ]

    pod_dict = spa_pod.build_spa_pod_dict("hello")
    assert pod_dict["type"] == spa_pod.SPA_TYPE_String
    assert spa_pod.parse_spa_pod_dict(pod_dict) == "hello"
    assert spa_pod.parse_spa_pod_dict({"data": "not-bytes"}) == {"data": "not-bytes"}


def test_typed_object_runtime_docs():
    assert "Typed SPA object" in (spa_pod.SpaProps.__doc__ or "")
    assert "attribute, string key, or numeric" in (spa_pod.SpaProps.volume.__doc__ or "")
    assert "typed Python objects" in (spa_pod.parse_spa_pod.__doc__ or "")
