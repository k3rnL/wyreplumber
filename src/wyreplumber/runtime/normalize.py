"""Normalize parsed SPA parameters into the detached runtime contract."""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Mapping, Sequence
from enum import Enum, IntEnum
from typing import Callable

from wyreplumber._spa_pod_types import (
    SPA_TYPE_Choice,
    SPA_TYPE_Struct,
    SpaAudioChannel,
    SpaAudioFormat,
    SpaAudioIec958Codec,
    SpaDirection,
    SpaMediaSubtype,
    SpaMediaType,
    SpaParamAvailability,
    _property_spec_by_key,
)

from .models import (
    AudioFormatValue,
    AudioPropertiesValue,
    Availability,
    ParameterValue,
    PortDirection,
    ProfileValue,
    RouteValue,
    RuntimeValue,
    SpaChoiceValue,
    SpaIdValue,
)


_MISSING = object()
_CHOICE_NAMES = {0: "none", 1: "range", 2: "step", 3: "enum", 4: "flags"}


def normalize_spa_parameter(
    *,
    owner_type: str,
    owner_id: int,
    parameter_id: str,
    permissions: str,
    values: Sequence[object],
) -> ParameterValue:
    """Normalize one enumerated WirePlumber parameter and all of its values."""

    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError("values must be a sequence")

    normalizer: Callable[[object], object]
    if parameter_id == "Props":
        normalizer = normalize_audio_properties
    elif parameter_id in {"Format", "EnumFormat"}:
        normalizer = normalize_audio_format
    elif parameter_id in {"Profile", "EnumProfile"}:
        normalizer = lambda value: normalize_profile(
            value,
            device_id=owner_id,
            active=parameter_id == "Profile",
        )
    elif parameter_id in {"Route", "EnumRoute"}:
        normalizer = lambda value: normalize_route(
            value,
            device_id=owner_id,
            active=parameter_id == "Route",
        )
    else:
        normalizer = normalize_spa_json

    return ParameterValue(
        owner_type=owner_type,
        owner_id=owner_id,
        id=parameter_id,
        permissions=permissions,
        values=tuple(normalizer(value) for value in values),
    )


def normalize_audio_properties(value: object) -> AudioPropertiesValue:
    """Normalize a SPA Props object used for node or route audio controls."""

    properties = _properties(value)
    volume = _take(properties, "volume")
    mute = _take(properties, "mute")
    channel_volumes = _take(properties, "channelVolumes", "channel_volumes")
    channel_map = _take(properties, "channelMap", "channel_map")
    monitor_mute = _take(properties, "monitorMute", "monitor_mute")
    monitor_volumes = _take(properties, "monitorVolumes", "monitor_volumes")
    soft_mute = _take(properties, "softMute", "soft_mute")
    soft_volumes = _take(properties, "softVolumes", "soft_volumes")

    return AudioPropertiesValue(
        volume=None if volume is _MISSING else _number(volume, "volume"),
        mute=None if mute is _MISSING else _bool(mute, "mute"),
        channel_volumes=()
        if channel_volumes is _MISSING
        else tuple(_number(item, "channel volume") for item in _array_values(channel_volumes)),
        channel_positions=()
        if channel_map is _MISSING
        else tuple(
            _spa_id(item, SpaAudioChannel, "SpaAudioChannel")
            for item in _array_values(channel_map)
        ),
        monitor_mute=None
        if monitor_mute is _MISSING
        else _bool(monitor_mute, "monitor mute"),
        monitor_volumes=()
        if monitor_volumes is _MISSING
        else tuple(_number(item, "monitor volume") for item in _array_values(monitor_volumes)),
        soft_mute=None if soft_mute is _MISSING else _bool(soft_mute, "soft mute"),
        soft_volumes=()
        if soft_volumes is _MISSING
        else tuple(_number(item, "soft volume") for item in _array_values(soft_volumes)),
        extra=normalize_spa_json(properties),
    )


def normalize_audio_format(value: object) -> AudioFormatValue:
    """Normalize a SPA Format or EnumFormat object for audio orchestration."""

    properties = _properties(value)
    media_type = _take(properties, "mediaType", "media_type")
    media_subtype = _take(properties, "mediaSubtype", "media_subtype")
    sample_format = _take(properties, "audio_format", "format")
    rate = _take(properties, "audio_rate", "rate")
    channels = _take(properties, "audio_channels", "channels")
    positions = _take(properties, "audio_position", "position", "positions")
    iec958_codec = _take(properties, "audio_iec958Codec", "iec958Codec", "iec958_codec")

    return AudioFormatValue(
        media_type=None
        if media_type is _MISSING
        else _choice_or_id(media_type, SpaMediaType, "SpaMediaType"),
        media_subtype=None
        if media_subtype is _MISSING
        else _choice_or_id(media_subtype, SpaMediaSubtype, "SpaMediaSubtype"),
        sample_format=None
        if sample_format is _MISSING
        else _choice_or_id(sample_format, SpaAudioFormat, "SpaAudioFormat"),
        rate=None if rate is _MISSING else _choice_or_int(rate, "rate"),
        channels=None if channels is _MISSING else _choice_or_int(channels, "channels"),
        positions=()
        if positions is _MISSING
        else tuple(
            _spa_id(item, SpaAudioChannel, "SpaAudioChannel")
            for item in _array_values(positions)
        ),
        iec958_codec=None
        if iec958_codec is _MISSING
        else _choice_or_id(iec958_codec, SpaAudioIec958Codec, "SpaAudioIec958Codec"),
        extra=normalize_spa_json(properties),
    )


def normalize_profile(value: object, *, device_id: int, active: bool) -> ProfileValue:
    """Normalize a SPA Profile or EnumProfile object."""

    properties = _properties(value)
    index = _required(properties, "index")
    name = _required(properties, "name")
    description = _take(properties, "description")
    priority = _take(properties, "priority")
    available = _take(properties, "available")
    classes = _take(properties, "classes")

    return ProfileValue(
        device_id=device_id,
        index=_int(index, "profile index"),
        name=_str(name, "profile name"),
        description=None if description is _MISSING else _str(description, "profile description"),
        priority=0 if priority is _MISSING else _int(priority, "profile priority"),
        available=Availability.UNKNOWN
        if available is _MISSING
        else _availability(available),
        active=active,
        classes=()
        if classes is _MISSING
        else tuple(_profile_class(item) for item in _array_values(classes)),
        properties=normalize_spa_json(properties),
    )


def normalize_route(value: object, *, device_id: int, active: bool) -> RouteValue:
    """Normalize a SPA Route or EnumRoute object and its writable audio props."""

    properties = _properties(value)
    index = _required(properties, "index")
    direction = _required(properties, "direction")
    name = _required(properties, "name")
    description = _take(properties, "description")
    priority = _take(properties, "priority")
    available = _take(properties, "available")
    profiles = _take(properties, "profiles")
    route_props = _take(properties, "props")
    spa_device = _take(properties, "device")

    audio_properties = (
        AudioPropertiesValue()
        if route_props is _MISSING
        else normalize_audio_properties(route_props)
    )
    if spa_device is not _MISSING:
        properties["spa_device_index"] = _int(spa_device, "route SPA device index")

    return RouteValue(
        device_id=device_id,
        index=_int(index, "route index"),
        direction=_direction(direction),
        name=_str(name, "route name"),
        description=None if description is _MISSING else _str(description, "route description"),
        priority=0 if priority is _MISSING else _int(priority, "route priority"),
        available=Availability.UNKNOWN
        if available is _MISSING
        else _availability(available),
        active=active,
        profile_ids=()
        if profiles is _MISSING
        else tuple(_int(item, "route profile index") for item in _array_values(profiles)),
        volume=audio_properties.volume,
        mute=audio_properties.mute,
        channel_volumes=audio_properties.channel_volumes,
        channel_positions=audio_properties.channel_positions,
        properties={
            **normalize_spa_json(properties),
            **({"audio_extra": audio_properties.extra.to_dict()} if audio_properties.extra else {}),
        },
    )


def normalize_spa_json(value: object) -> object:
    """Convert arbitrary parsed SPA data to a lossless JSON-compatible form."""

    if isinstance(value, RuntimeValue):
        return value.to_dict()
    if isinstance(value, IntEnum):
        return {
            "id": int(value),
            "name": value.name,
            "namespace": type(value).__name__,
        }
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            "encoding": "base64",
            "data": b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, Mapping):
        object_id = _object_id(value)
        result: dict[str, object] = {}
        for key, item in value.items():
            result[_property_name(key, object_id)] = normalize_spa_json(item)
        return result
    if isinstance(value, Sequence):
        return [normalize_spa_json(item) for item in value]
    raise TypeError(f"SPA value of type {type(value).__name__!r} is not normalizable")


def _properties(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("SPA object must be a mapping or SpaPodObject")
    object_id = _object_id(value)
    nested = value.get("properties")
    source = nested if isinstance(nested, Mapping) else value
    return {
        _property_name(key, object_id): item
        for key, item in source.items()
        if key not in {"_pod_type", "_object_type", "_object_id", "object_type", "object_id"}
    }


def _object_id(value: Mapping[object, object]) -> int | None:
    candidate = getattr(value, "object_id", None)
    if candidate is None:
        candidate = value.get("object_id", value.get("_object_id"))
    return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) else None


def _property_name(key: object, object_id: int | None) -> str:
    if isinstance(key, str):
        return key
    if isinstance(key, int) and object_id is not None:
        spec = _property_spec_by_key(object_id, key)
        if spec is not None:
            return spec.name
    return str(key)


def _take(values: dict[str, object], *names: str) -> object:
    for name in names:
        if name in values:
            return values.pop(name)
    return _MISSING


def _required(values: dict[str, object], *names: str) -> object:
    value = _take(values, *names)
    if value is _MISSING:
        raise ValueError(f"SPA value is missing required field {names[0]!r}")
    return value


def _choice_or_id(value: object, enum_type: type[IntEnum], namespace: str) -> SpaIdValue | SpaChoiceValue:
    if _is_choice(value):
        return _choice(value, lambda item: _spa_id(item, enum_type, namespace))
    return _spa_id(value, enum_type, namespace)


def _choice_or_int(value: object, name: str) -> int | SpaChoiceValue:
    if _is_choice(value):
        return _choice(value, lambda item: _int(item, name))
    return _int(value, name)


def _choice(value: object, item_normalizer: Callable[[object], object]) -> SpaChoiceValue:
    if not isinstance(value, Mapping):
        raise TypeError("SPA choice must be a mapping")
    choice = dict(value)
    raw_kind = choice.pop("kind", choice.pop("choice_type", 0))
    if isinstance(raw_kind, str):
        kind = raw_kind.lower()
    else:
        kind = _CHOICE_NAMES.get(_int(raw_kind, "choice type"), f"unknown:{raw_kind}")
    choice.pop("_pod_type", None)
    flags = choice.pop("flags", 0)
    choice.pop("child_size", None)
    choice.pop("child_type", None)
    values = choice.pop("values", ())
    sequence = _array_values(values)

    default = choice.pop("default", sequence[0] if sequence else None)
    minimum = choice.pop("min", sequence[1] if kind in {"range", "step"} and len(sequence) > 1 else None)
    maximum = choice.pop("max", sequence[2] if kind in {"range", "step"} and len(sequence) > 2 else None)
    step = choice.pop("step", sequence[3] if kind == "step" and len(sequence) > 3 else None)
    raw_alternatives = choice.pop(
        "alternatives",
        sequence[1:] if kind in {"enum", "flags"} else (),
    )

    return SpaChoiceValue(
        kind=kind,
        default=None if default is None else item_normalizer(default),
        minimum=None if minimum is None else item_normalizer(minimum),
        maximum=None if maximum is None else item_normalizer(maximum),
        step=None if step is None else item_normalizer(step),
        alternatives=tuple(item_normalizer(item) for item in _array_values(raw_alternatives)),
        flags=_int(flags, "choice flags"),
        extra=normalize_spa_json(choice),
    )


def _is_choice(value: object) -> bool:
    return isinstance(value, Mapping) and (
        "choice_type" in value
        or "kind" in value
        or value.get("_pod_type") == SPA_TYPE_Choice
    )


def _spa_id(value: object, enum_type: type[IntEnum], namespace: str) -> SpaIdValue:
    if isinstance(value, str):
        try:
            raw_id = int(enum_type[value.upper()])
        except (KeyError, ValueError):
            try:
                raw_id = int(value)
            except ValueError as error:
                raise ValueError(f"invalid {namespace} value {value!r}") from error
    else:
        raw_id = _int(value, namespace)
    try:
        name = enum_type(raw_id).name
    except ValueError:
        name = None
    return SpaIdValue(namespace=namespace, id=raw_id, name=name)


def _array_values(value: object) -> tuple[object, ...]:
    if _is_choice(value):
        assert isinstance(value, Mapping)
        selected = value.get("default", value.get("value", _MISSING))
        if selected is _MISSING:
            candidates = value.get("values", ())
            if isinstance(candidates, Sequence) and candidates:
                selected = candidates[0]
        if selected is _MISSING:
            return ()
        return _array_values(selected)
    if isinstance(value, Mapping):
        if "values" not in value:
            raise TypeError("SPA array mapping must contain values")
        value = value["values"]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("SPA array value must be a sequence")
    return tuple(value)


def _availability(value: object) -> Availability:
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"yes", "no", "unknown"}:
            return Availability(lowered)
        try:
            value = int(value)
        except ValueError as error:
            raise ValueError(f"invalid availability {value!r}") from error
    raw = _int(value, "availability")
    return {
        int(SpaParamAvailability.YES): Availability.YES,
        int(SpaParamAvailability.NO): Availability.NO,
        int(SpaParamAvailability.UNKNOWN): Availability.UNKNOWN,
    }.get(raw, Availability.UNKNOWN)


def _direction(value: object) -> PortDirection:
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"input", "output", "unknown"}:
            return PortDirection(lowered)
        try:
            value = int(value)
        except ValueError as error:
            raise ValueError(f"invalid direction {value!r}") from error
    raw = _int(value, "direction")
    if raw == int(SpaDirection.INPUT):
        return PortDirection.INPUT
    if raw == int(SpaDirection.OUTPUT):
        return PortDirection.OUTPUT
    return PortDirection.UNKNOWN


def _profile_class(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("name", "media.class", "media_class", "class"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        # Be defensive when a caller supplies an unspecialized native
        # profile-class struct. Its first member is the media class.
        if value.get("_pod_type") == SPA_TYPE_Struct:
            members = value.get("values")
            if (
                isinstance(members, Sequence)
                and not isinstance(members, (str, bytes, bytearray))
                and members
                and isinstance(members[0], str)
                and members[0]
            ):
                return members[0]
    raise TypeError(f"invalid profile class {value!r}")


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    return float(value)


def _int(value: object, name: str) -> int:
    if isinstance(value, IntEnum):
        return int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value
