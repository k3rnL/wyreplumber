"""Build immutable runtime snapshots from the native primitive payload."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace

from wyreplumber.spa_pod import parse_spa_pod_dict

from .models import (
    ConnectionHealthValue,
    ConnectionState,
    DefaultsValue,
    DefaultTargetValue,
    DeviceValue,
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
)
from .normalize import normalize_spa_json, normalize_spa_parameter


NATIVE_RUNTIME_PAYLOAD_VERSION = 1

_REQUIRED_PAYLOAD_FIELDS = {
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

_NODE_STATES = {
    -1: NodeState.ERROR,
    0: NodeState.CREATING,
    1: NodeState.SUSPENDED,
    2: NodeState.IDLE,
    3: NodeState.RUNNING,
}

_LINK_STATES = {
    -2: "error",
    -1: "unlinked",
    0: "init",
    1: "negotiating",
    2: "allocating",
    3: "paused",
    4: "active",
}


class RuntimePayloadError(ValueError):
    """A structured failure while validating or converting a native payload."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


def capture_runtime_snapshot(connection: object) -> RuntimeSnapshot:
    """Capture and convert one payload from a native ``WPConnection``."""

    capture = getattr(connection, "capture_runtime_payload", None)
    if not callable(capture):
        raise TypeError("connection must provide capture_runtime_payload()")
    return runtime_snapshot_from_payload(capture())


def runtime_snapshot_from_payload(payload: Mapping[str, object]) -> RuntimeSnapshot:
    """Validate one native payload and construct a fully detached snapshot."""

    if not isinstance(payload, Mapping):
        raise RuntimePayloadError("invalid_payload", "payload must be a mapping")
    _validate_detached(payload)
    missing = _REQUIRED_PAYLOAD_FIELDS - set(payload)
    unknown = set(payload) - _REQUIRED_PAYLOAD_FIELDS
    if missing:
        raise RuntimePayloadError(
            "missing_fields",
            f"missing payload field(s): {', '.join(sorted(missing))}",
        )
    if unknown:
        raise RuntimePayloadError(
            "unknown_fields",
            f"unknown payload field(s): {', '.join(sorted(unknown))}",
        )
    version = _integer(payload["payload_version"], "$.payload_version")
    if version != NATIVE_RUNTIME_PAYLOAD_VERSION:
        raise RuntimePayloadError(
            "unsupported_payload_version",
            f"expected {NATIVE_RUNTIME_PAYLOAD_VERSION}, received {version}",
            path="$.payload_version",
        )

    generation = _identifier(payload["generation"], "$.generation")
    sequence = _identifier(payload["sequence"], "$.sequence")
    health = _health(payload["health"], generation)
    parameter_values = _parameters(payload["parameters"])

    profiles_by_key: dict[tuple[int, int], ProfileValue] = {}
    routes_by_key: dict[tuple[int, int], RouteValue] = {}
    for parameter in parameter_values:
        for value in parameter.values:
            if isinstance(value, ProfileValue):
                _merge_active(profiles_by_key, (value.device_id, value.index), value)
            elif isinstance(value, RouteValue):
                _merge_active(routes_by_key, (value.device_id, value.index), value)

    port_values = _ports(payload["ports"])
    input_ports: dict[int, list[int]] = defaultdict(list)
    output_ports: dict[int, list[int]] = defaultdict(list)
    for port in port_values:
        target = input_ports if port.direction is PortDirection.INPUT else output_ports
        target[port.node_id].append(port.id)

    device_values = _devices(
        payload["devices"],
        profiles_by_key=profiles_by_key,
        routes_by_key=routes_by_key,
    )
    node_values = _nodes(payload["nodes"], input_ports, output_ports)
    link_values = _links(payload["links"])
    metadata_values = _metadata(payload["metadata"])
    defaults = _defaults(payload["defaults"], node_values)

    try:
        return RuntimeSnapshot(
            generation=generation,
            sequence=sequence,
            captured_at=_string(payload["captured_at"], "$.captured_at"),
            health=health,
            devices=device_values,
            nodes=node_values,
            ports=port_values,
            links=link_values,
            metadata=metadata_values,
            parameters=parameter_values,
            profiles=tuple(profiles_by_key.values()),
            routes=tuple(routes_by_key.values()),
            defaults=defaults,
        )
    except (TypeError, ValueError) as error:
        raise RuntimePayloadError("invalid_snapshot", str(error)) from error


def _health(value: object, generation: int) -> ConnectionHealthValue:
    health = _mapping(value, "$.health")
    state_value = _string(_required(health, "state", "$.health"), "$.health.state")
    try:
        state = ConnectionState(state_value)
    except ValueError as error:
        raise RuntimePayloadError(
            "invalid_health_state",
            f"unknown connection state {state_value!r}",
            path="$.health.state",
        ) from error
    health_generation = _identifier(
        _required(health, "generation", "$.health"),
        "$.health.generation",
    )
    if health_generation != generation:
        raise RuntimePayloadError(
            "mixed_generation",
            "health and payload generations differ",
            path="$.health.generation",
        )
    reason = health.get("reason")
    if reason is not None:
        reason = _string(reason, "$.health.reason")
    details = health.get("details", {})
    return ConnectionHealthValue(
        state=state,
        generation=generation,
        reason=reason,
        details=_mapping(details, "$.health.details"),
    )


def _parameters(value: object) -> tuple[ParameterValue, ...]:
    records = _sequence(value, "$.parameters")
    result: list[ParameterValue] = []
    for index, item in enumerate(records):
        path = f"$.parameters[{index}]"
        record = _mapping(item, path)
        raw_values = _sequence(_required(record, "values", path), f"{path}.values")
        parsed_values: list[object] = []
        for value_index, raw_value in enumerate(raw_values):
            value_path = f"{path}.values[{value_index}]"
            if not isinstance(raw_value, Mapping):
                raise RuntimePayloadError(
                    "invalid_parameter_value",
                    "raw SPA value must be a mapping",
                    path=value_path,
                )
            parsed_values.append(parse_spa_pod_dict(dict(raw_value)))
        try:
            parameter = normalize_spa_parameter(
                owner_type=_string(_required(record, "owner_type", path), f"{path}.owner_type"),
                owner_id=_identifier(_required(record, "owner_id", path), f"{path}.owner_id"),
                parameter_id=_string(_required(record, "id", path), f"{path}.id"),
                permissions=_string(
                    _required(record, "permissions", path),
                    f"{path}.permissions",
                    allow_empty=True,
                ),
                values=parsed_values,
            )
            complete = record.get("complete", True)
            if not isinstance(complete, bool):
                raise TypeError("complete must be a boolean")
            parameter = replace(parameter, properties={"complete": complete})
        except (TypeError, ValueError) as error:
            raise RuntimePayloadError(
                "parameter_normalization_failed",
                str(error),
                path=path,
            ) from error
        result.append(parameter)
    return tuple(result)


def _devices(
    value: object,
    *,
    profiles_by_key: Mapping[tuple[int, int], ProfileValue],
    routes_by_key: Mapping[tuple[int, int], RouteValue],
) -> tuple[DeviceValue, ...]:
    result: list[DeviceValue] = []
    for index, item in enumerate(_sequence(value, "$.devices")):
        path = f"$.devices[{index}]"
        record = _mapping(item, path)
        object_id = _identifier(_required(record, "id", path), f"{path}.id")
        properties = _properties(record, path)
        result.append(
            DeviceValue(
                id=object_id,
                name=_property(properties, "device.name"),
                description=_property(properties, "device.description", "device.nick"),
                media_class=_property(properties, "media.class"),
                properties=properties,
                parameter_ids=_string_sequence(record.get("parameter_ids", ()), f"{path}.parameter_ids"),
                profile_ids=tuple(
                    profile_id
                    for device_id, profile_id in profiles_by_key
                    if device_id == object_id
                ),
                route_ids=tuple(
                    route_id
                    for device_id, route_id in routes_by_key
                    if device_id == object_id
                ),
            )
        )
    return tuple(result)


def _nodes(
    value: object,
    input_ports: Mapping[int, Sequence[int]],
    output_ports: Mapping[int, Sequence[int]],
) -> tuple[NodeValue, ...]:
    result: list[NodeValue] = []
    for index, item in enumerate(_sequence(value, "$.nodes")):
        path = f"$.nodes[{index}]"
        record = _mapping(item, path)
        object_id = _identifier(_required(record, "id", path), f"{path}.id")
        properties = _properties(record, path)
        raw_state = _integer(record.get("state", -99), f"{path}.state")
        result.append(
            NodeValue(
                id=object_id,
                device_id=_property_identifier(properties, "device.id", f"{path}.properties.device.id"),
                name=_property(properties, "node.name"),
                description=_property(properties, "node.description", "node.nick"),
                media_class=_property(properties, "media.class"),
                state=_NODE_STATES.get(raw_state, NodeState.UNKNOWN),
                error=_optional_string(record.get("error"), f"{path}.error"),
                input_port_ids=tuple(sorted(input_ports.get(object_id, ()))),
                output_port_ids=tuple(sorted(output_ports.get(object_id, ()))),
                properties=properties,
                parameter_ids=_string_sequence(record.get("parameter_ids", ()), f"{path}.parameter_ids"),
            )
        )
    return tuple(result)


def _ports(value: object) -> tuple[PortValue, ...]:
    result: list[PortValue] = []
    for index, item in enumerate(_sequence(value, "$.ports")):
        path = f"$.ports[{index}]"
        record = _mapping(item, path)
        properties = _properties(record, path)
        direction_value = _integer(_required(record, "direction", path), f"{path}.direction")
        direction = {
            0: PortDirection.INPUT,
            1: PortDirection.OUTPUT,
        }.get(direction_value, PortDirection.UNKNOWN)
        node_id = _property_identifier(properties, "node.id", f"{path}.properties.node.id")
        if node_id is None:
            raise RuntimePayloadError(
                "missing_relationship",
                "port has no node.id property",
                path=f"{path}.properties.node.id",
            )
        result.append(
            PortValue(
                id=_identifier(_required(record, "id", path), f"{path}.id"),
                node_id=node_id,
                direction=direction,
                name=_property(properties, "port.name", "port.alias"),
                channel=_property(properties, "audio.channel"),
                properties=properties,
                parameter_ids=_string_sequence(record.get("parameter_ids", ()), f"{path}.parameter_ids"),
            )
        )
    return tuple(result)


def _links(value: object) -> tuple[LinkValue, ...]:
    result: list[LinkValue] = []
    for index, item in enumerate(_sequence(value, "$.links")):
        path = f"$.links[{index}]"
        record = _mapping(item, path)
        properties = _properties(record, path)
        raw_state = _integer(record.get("state", -99), f"{path}.state")
        result.append(
            LinkValue(
                id=_identifier(_required(record, "id", path), f"{path}.id"),
                output_node_id=_identifier(
                    _required(record, "output_node_id", path),
                    f"{path}.output_node_id",
                ),
                output_port_id=_identifier(
                    _required(record, "output_port_id", path),
                    f"{path}.output_port_id",
                ),
                input_node_id=_identifier(
                    _required(record, "input_node_id", path),
                    f"{path}.input_node_id",
                ),
                input_port_id=_identifier(
                    _required(record, "input_port_id", path),
                    f"{path}.input_port_id",
                ),
                state=_LINK_STATES.get(raw_state, f"unknown:{raw_state}"),
                owner=_property(properties, "open-cinema.owner"),
                desired_id=_property(properties, "open-cinema.desired-id"),
                properties=properties,
            )
        )
    return tuple(result)


def _metadata(value: object) -> tuple[MetadataValue, ...]:
    result: list[MetadataValue] = []
    for index, item in enumerate(_sequence(value, "$.metadata")):
        path = f"$.metadata[{index}]"
        record = _mapping(item, path)
        entries: list[MetadataEntryValue] = []
        for entry_index, entry_item in enumerate(
            _sequence(record.get("entries", ()), f"{path}.entries")
        ):
            entry_path = f"{path}.entries[{entry_index}]"
            entry = _mapping(entry_item, entry_path)
            entries.append(
                MetadataEntryValue(
                    subject=_identifier(
                        _required(entry, "subject", entry_path),
                        f"{entry_path}.subject",
                    ),
                    key=_string(_required(entry, "key", entry_path), f"{entry_path}.key"),
                    type_name=_optional_string(entry.get("type"), f"{entry_path}.type"),
                    value=_optional_string(entry.get("value"), f"{entry_path}.value"),
                )
            )
        result.append(
            MetadataValue(
                id=_identifier(_required(record, "id", path), f"{path}.id"),
                name=_optional_string(record.get("name"), f"{path}.name"),
                properties=_properties(record, path),
                entries=tuple(entries),
            )
        )
    return tuple(result)


def _defaults(value: object, nodes: Sequence[NodeValue]) -> DefaultsValue:
    entries = _sequence(value, "$.defaults")
    by_key: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    metadata_id: int | None = None
    for index, item in enumerate(entries):
        path = f"$.defaults[{index}]"
        entry = _mapping(item, path)
        key = _string(_required(entry, "key", path), f"{path}.key")
        by_key[key].append(entry)
        if metadata_id is None and entry.get("metadata_id") is not None:
            metadata_id = _identifier(entry["metadata_id"], f"{path}.metadata_id")

    nodes_by_name = {
        name: node.id
        for node in nodes
        if (name := node.name or _property(node.properties, "node.name"))
    }

    def target(media_class: str, key: str) -> DefaultTargetValue | None:
        configured_key = f"default.configured.{key.removeprefix('default.')}"
        actual_name = _default_name(by_key.get(key, ()))
        configured_name = _default_name(by_key.get(configured_key, ())) or actual_name
        if configured_name is None and actual_name is None:
            return None
        return DefaultTargetValue(
            media_class=media_class,
            configured_name=configured_name,
            resolved_node_id=nodes_by_name.get(actual_name) if actual_name else None,
        )

    extra = {
        key: [normalize_spa_json(dict(entry)) for entry in key_entries]
        for key, key_entries in by_key.items()
    }
    return DefaultsValue(
        metadata_id=metadata_id,
        audio_sink=target("Audio/Sink", "default.audio.sink"),
        audio_source=target("Audio/Source", "default.audio.source"),
        video_source=target("Video/Source", "default.video.source"),
        extra=extra,
    )


def _default_name(entries: Sequence[Mapping[str, object]]) -> str | None:
    for entry in reversed(entries):
        value = entry.get("value")
        if not isinstance(value, str) or not value:
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(decoded, str):
            return decoded
        if isinstance(decoded, Mapping) and isinstance(decoded.get("name"), str):
            return decoded["name"]
    return None


def _merge_active(
    values: dict[tuple[int, int], ProfileValue | RouteValue],
    key: tuple[int, int],
    value: ProfileValue | RouteValue,
) -> None:
    previous = values.get(key)
    if previous is None or (value.active and not previous.active):
        values[key] = value


def _properties(record: Mapping[str, object], path: str) -> Mapping[str, object]:
    return _mapping(record.get("properties", {}), f"{path}.properties")


def _property(properties: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = properties.get(key)
        if isinstance(value, str):
            return value
    return None


def _property_identifier(
    properties: Mapping[str, object],
    key: str,
    path: str,
) -> int | None:
    value = properties.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError as error:
            raise RuntimePayloadError(
                "invalid_identifier",
                f"expected an integer string, received {value!r}",
                path=path,
            ) from error
    return _identifier(value, path)


def _required(values: Mapping[str, object], key: str, path: str) -> object:
    if key not in values:
        raise RuntimePayloadError(
            "missing_field",
            f"missing required field {key!r}",
            path=path,
        )
    return values[key]


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimePayloadError("invalid_mapping", "expected a string-keyed mapping", path=path)
    return value


def _sequence(value: object, path: str) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise RuntimePayloadError("invalid_sequence", "expected a sequence", path=path)
    return tuple(value)


def _string(value: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RuntimePayloadError("invalid_string", "expected a string", path=path)
    if not allow_empty and not value:
        raise RuntimePayloadError("invalid_string", "string must not be empty", path=path)
    return value


def _optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path, allow_empty=True)


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimePayloadError("invalid_integer", "expected an integer", path=path)
    return value


def _identifier(value: object, path: str) -> int:
    result = _integer(value, path)
    if result < 0:
        raise RuntimePayloadError("invalid_identifier", "identifier must be non-negative", path=path)
    return result


def _string_sequence(value: object, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(value, path))
    )


def _validate_detached(value: object, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RuntimePayloadError(
                    "native_object_leak",
                    "payload mappings must use string keys",
                    path=path,
                )
            _validate_detached(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_detached(item, path=f"{path}[{index}]")
        return
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return
    raise RuntimePayloadError(
        "native_object_leak",
        f"payload contains unsupported object {type(value).__name__}",
        path=path,
    )
