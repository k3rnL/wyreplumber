"""Detached value objects for the WyrePlumber orchestration contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import ClassVar, Self

from ._immutable import FrozenDict, freeze_json


RUNTIME_VALUE_SCHEMA_VERSION = 1


class RuntimeValueDecodeError(ValueError):
    """A machine-readable failure while restoring a serialized runtime value."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code} at {path}: {message}")


_VALUE_TYPES: dict[str, type[RuntimeValue]] = {}


class RuntimeValue:
    """Serialization behavior shared by all detached runtime values."""

    VALUE_TYPE: ClassVar[str]
    SCHEMA_VERSION: ClassVar[int] = RUNTIME_VALUE_SCHEMA_VERSION

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        value_type = getattr(cls, "VALUE_TYPE", None)
        if not isinstance(value_type, str) or not value_type:
            raise TypeError("RuntimeValue subclasses must define VALUE_TYPE")
        existing = _VALUE_TYPES.get(value_type)
        if existing is not None and (
            existing.__module__ != cls.__module__
            or existing.__qualname__ != cls.__qualname__
        ):
            raise TypeError(f"duplicate runtime value type: {value_type}")
        _VALUE_TYPES[value_type] = cls

    def to_dict(self) -> dict[str, object]:
        """Serialize this value into the versioned JSON contract."""

        result: dict[str, object] = {
            "schema_version": self.SCHEMA_VERSION,
            "value_type": self.VALUE_TYPE,
        }
        for item in fields(self):
            if not item.metadata.get("serialize", True):
                continue
            value = getattr(self, item.name)
            if item.metadata.get("omit_none") and value is None:
                continue
            result[item.name] = _serialize(value)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        """Restore and validate this concrete value from its JSON contract."""

        decoded = runtime_value_from_dict(value)
        if not isinstance(decoded, cls):
            raise RuntimeValueDecodeError(
                "unexpected_value_type",
                f"expected {cls.VALUE_TYPE!r}, received {decoded.VALUE_TYPE!r}",
            )
        return decoded


class ConnectionState(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    STOPPED = "stopped"


class NodeState(str, Enum):
    ERROR = "error"
    CREATING = "creating"
    SUSPENDED = "suspended"
    IDLE = "idle"
    RUNNING = "running"
    UNKNOWN = "unknown"


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    UNKNOWN = "unknown"


class Availability(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SpaIdValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "spa_id"

    namespace: str
    id: int
    name: str | None = None

    def __post_init__(self) -> None:
        _required_string(self.namespace, "namespace")
        _identifier(self.id, "id")
        _optional_string(self.name, "name")


@dataclass(frozen=True, slots=True)
class SpaChoiceValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "spa_choice"

    kind: str
    default: object = None
    minimum: object = None
    maximum: object = None
    step: object = None
    alternatives: tuple[object, ...] = ()
    flags: int = 0
    extra: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _required_string(self.kind, "kind")
        for name in ("default", "minimum", "maximum", "step"):
            object.__setattr__(self, name, _contract_value(getattr(self, name)))
        if not isinstance(self.alternatives, Sequence) or isinstance(
            self.alternatives, (str, bytes, bytearray)
        ):
            raise TypeError("alternatives must be a sequence")
        object.__setattr__(
            self,
            "alternatives",
            tuple(_contract_value(item) for item in self.alternatives),
        )
        _identifier(self.flags, "flags")
        object.__setattr__(self, "extra", _mapping(self.extra, "extra"))


@dataclass(frozen=True, slots=True)
class AudioPropertiesValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "audio_properties"

    volume: float | None = None
    mute: bool | None = None
    channel_volumes: tuple[float, ...] = ()
    channel_positions: tuple[SpaIdValue, ...] = ()
    monitor_mute: bool | None = None
    monitor_volumes: tuple[float, ...] = ()
    soft_mute: bool | None = None
    soft_volumes: tuple[float, ...] = ()
    extra: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "volume", _optional_float(self.volume, "volume"))
        _optional_boolean(self.mute, "mute")
        object.__setattr__(self, "channel_volumes", _floats(self.channel_volumes, "channel_volumes"))
        object.__setattr__(
            self,
            "channel_positions",
            _runtime_values(self.channel_positions, SpaIdValue, "channel_positions"),
        )
        _optional_boolean(self.monitor_mute, "monitor_mute")
        object.__setattr__(self, "monitor_volumes", _floats(self.monitor_volumes, "monitor_volumes"))
        _optional_boolean(self.soft_mute, "soft_mute")
        object.__setattr__(self, "soft_volumes", _floats(self.soft_volumes, "soft_volumes"))
        object.__setattr__(self, "extra", _mapping(self.extra, "extra"))


@dataclass(frozen=True, slots=True)
class AudioFormatValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "audio_format"

    media_type: SpaIdValue | SpaChoiceValue | None = None
    media_subtype: SpaIdValue | SpaChoiceValue | None = None
    sample_format: SpaIdValue | SpaChoiceValue | None = None
    rate: int | SpaChoiceValue | None = None
    channels: int | SpaChoiceValue | None = None
    positions: tuple[SpaIdValue, ...] = ()
    iec958_codec: SpaIdValue | SpaChoiceValue | None = None
    extra: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        for name in ("media_type", "media_subtype", "sample_format", "iec958_codec"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, (SpaIdValue, SpaChoiceValue)):
                raise TypeError(f"{name} must be a SpaIdValue, SpaChoiceValue, or None")
        for name in ("rate", "channels"):
            value = getattr(self, name)
            if isinstance(value, SpaChoiceValue) or value is None:
                continue
            _identifier(value, name)
        object.__setattr__(self, "positions", _runtime_values(self.positions, SpaIdValue, "positions"))
        object.__setattr__(self, "extra", _mapping(self.extra, "extra"))


@dataclass(frozen=True, slots=True)
class ConnectionHealthValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "connection_health"

    state: ConnectionState
    generation: int
    reason: str | None = None
    details: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _enum(ConnectionState, self.state, "state"))
        _identifier(self.generation, "generation")
        _optional_string(self.reason, "reason")
        object.__setattr__(self, "details", _mapping(self.details, "details"))


@dataclass(frozen=True, slots=True)
class DeviceValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "device"

    id: int
    name: str | None = None
    description: str | None = None
    media_class: str | None = None
    properties: FrozenDict = field(default_factory=FrozenDict)
    parameter_ids: tuple[str, ...] = ()
    profile_ids: tuple[int, ...] = ()
    route_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, "id")
        _optional_strings(self, "name", "description", "media_class")
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))
        object.__setattr__(self, "parameter_ids", _strings(self.parameter_ids, "parameter_ids"))
        object.__setattr__(self, "profile_ids", _identifiers(self.profile_ids, "profile_ids"))
        object.__setattr__(self, "route_ids", _identifiers(self.route_ids, "route_ids"))


@dataclass(frozen=True, slots=True)
class NodeValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "node"

    id: int
    device_id: int | None = None
    name: str | None = None
    description: str | None = None
    media_class: str | None = None
    state: NodeState = NodeState.UNKNOWN
    error: str | None = None
    input_port_ids: tuple[int, ...] = ()
    output_port_ids: tuple[int, ...] = ()
    properties: FrozenDict = field(default_factory=FrozenDict)
    parameter_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, "id")
        _optional_identifier(self.device_id, "device_id")
        _optional_strings(self, "name", "description", "media_class", "error")
        object.__setattr__(self, "state", _enum(NodeState, self.state, "state"))
        object.__setattr__(self, "input_port_ids", _identifiers(self.input_port_ids, "input_port_ids"))
        object.__setattr__(self, "output_port_ids", _identifiers(self.output_port_ids, "output_port_ids"))
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))
        object.__setattr__(self, "parameter_ids", _strings(self.parameter_ids, "parameter_ids"))


@dataclass(frozen=True, slots=True)
class PortValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "port"

    id: int
    node_id: int
    direction: PortDirection
    name: str | None = None
    channel: str | None = None
    properties: FrozenDict = field(default_factory=FrozenDict)
    parameter_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, "id")
        _identifier(self.node_id, "node_id")
        object.__setattr__(self, "direction", _enum(PortDirection, self.direction, "direction"))
        _optional_strings(self, "name", "channel")
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))
        object.__setattr__(self, "parameter_ids", _strings(self.parameter_ids, "parameter_ids"))


@dataclass(frozen=True, slots=True)
class LinkValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "link"

    id: int
    output_node_id: int
    output_port_id: int
    input_node_id: int
    input_port_id: int
    state: str | None = None
    owner: str | None = None
    desired_id: str | None = None
    properties: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        for name in ("id", "output_node_id", "output_port_id", "input_node_id", "input_port_id"):
            _identifier(getattr(self, name), name)
        _optional_strings(self, "state", "owner", "desired_id")
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))


@dataclass(frozen=True, slots=True)
class MetadataEntryValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "metadata_entry"

    subject: int
    key: str
    type_name: str | None
    value: str | None

    def __post_init__(self) -> None:
        _identifier(self.subject, "subject")
        _required_string(self.key, "key")
        _optional_string(self.type_name, "type_name")
        _optional_string(self.value, "value")


@dataclass(frozen=True, slots=True)
class MetadataValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "metadata"

    id: int
    name: str | None = None
    properties: FrozenDict = field(default_factory=FrozenDict)
    entries: tuple[MetadataEntryValue, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, "id")
        _optional_string(self.name, "name")
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))
        object.__setattr__(self, "entries", _runtime_values(self.entries, MetadataEntryValue, "entries"))


@dataclass(frozen=True, slots=True)
class ParameterValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "parameter"

    owner_type: str
    owner_id: int
    id: str
    permissions: str
    values: tuple[object, ...] = ()
    properties: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _required_string(self.owner_type, "owner_type")
        _identifier(self.owner_id, "owner_id")
        _required_string(self.id, "id")
        _required_string(self.permissions, "permissions", allow_empty=True)
        if not isinstance(self.values, Sequence) or isinstance(self.values, (str, bytes, bytearray)):
            raise TypeError("values must be a sequence")
        object.__setattr__(self, "values", tuple(_contract_value(item) for item in self.values))
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))


@dataclass(frozen=True, slots=True)
class ProfileValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "profile"

    device_id: int
    index: int
    name: str
    description: str | None = None
    priority: int = 0
    available: Availability = Availability.UNKNOWN
    active: bool = False
    classes: tuple[str, ...] = ()
    properties: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _identifier(self.device_id, "device_id")
        _identifier(self.index, "index")
        _required_string(self.name, "name")
        _optional_string(self.description, "description")
        _integer(self.priority, "priority")
        object.__setattr__(self, "available", _enum(Availability, self.available, "available"))
        _boolean(self.active, "active")
        object.__setattr__(self, "classes", _strings(self.classes, "classes"))
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))


@dataclass(frozen=True, slots=True)
class RouteValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "route"

    device_id: int
    index: int
    direction: PortDirection
    name: str
    description: str | None = None
    priority: int = 0
    available: Availability = Availability.UNKNOWN
    active: bool = False
    profile_ids: tuple[int, ...] = ()
    volume: float | None = None
    mute: bool | None = None
    channel_volumes: tuple[float, ...] = ()
    channel_positions: tuple[SpaIdValue, ...] = ()
    properties: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _identifier(self.device_id, "device_id")
        _identifier(self.index, "index")
        object.__setattr__(self, "direction", _enum(PortDirection, self.direction, "direction"))
        _required_string(self.name, "name")
        _optional_string(self.description, "description")
        _integer(self.priority, "priority")
        object.__setattr__(self, "available", _enum(Availability, self.available, "available"))
        _boolean(self.active, "active")
        object.__setattr__(self, "profile_ids", _identifiers(self.profile_ids, "profile_ids"))
        object.__setattr__(self, "volume", _optional_float(self.volume, "volume"))
        _optional_boolean(self.mute, "mute")
        object.__setattr__(self, "channel_volumes", _floats(self.channel_volumes, "channel_volumes"))
        object.__setattr__(
            self,
            "channel_positions",
            _runtime_values(self.channel_positions, SpaIdValue, "channel_positions"),
        )
        object.__setattr__(self, "properties", _mapping(self.properties, "properties"))


@dataclass(frozen=True, slots=True)
class DefaultTargetValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "default_target"

    media_class: str
    configured_name: str | None = None
    resolved_node_id: int | None = None

    def __post_init__(self) -> None:
        _required_string(self.media_class, "media_class")
        _optional_string(self.configured_name, "configured_name")
        _optional_identifier(self.resolved_node_id, "resolved_node_id")


@dataclass(frozen=True, slots=True)
class DefaultsValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "defaults"

    metadata_id: int | None = None
    audio_sink: DefaultTargetValue | None = None
    audio_source: DefaultTargetValue | None = None
    video_source: DefaultTargetValue | None = None
    extra: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _optional_identifier(self.metadata_id, "metadata_id")
        for name in ("audio_sink", "audio_source", "video_source"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, DefaultTargetValue):
                raise TypeError(f"{name} must be a DefaultTargetValue or None")
        object.__setattr__(self, "extra", _mapping(self.extra, "extra"))


@dataclass(frozen=True, slots=True)
class UnresolvedRelationshipValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "unresolved_relationship"

    source_type: str
    source_id: int | str
    relation: str
    target_type: str
    target_id: int | str
    reason: str

    def __post_init__(self) -> None:
        _required_string(self.source_type, "source_type")
        _identity(self.source_id, "source_id")
        _required_string(self.relation, "relation")
        _required_string(self.target_type, "target_type")
        _identity(self.target_id, "target_id")
        _required_string(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "runtime_snapshot"

    generation: int
    sequence: int
    captured_at: str
    health: ConnectionHealthValue
    devices: tuple[DeviceValue, ...] = ()
    nodes: tuple[NodeValue, ...] = ()
    ports: tuple[PortValue, ...] = ()
    links: tuple[LinkValue, ...] = ()
    metadata: tuple[MetadataValue, ...] = ()
    parameters: tuple[ParameterValue, ...] = ()
    profiles: tuple[ProfileValue, ...] = ()
    routes: tuple[RouteValue, ...] = ()
    defaults: DefaultsValue = field(default_factory=DefaultsValue)
    unresolved_relationships: tuple[UnresolvedRelationshipValue, ...] = ()
    devices_by_id: Mapping[int, DeviceValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    nodes_by_id: Mapping[int, NodeValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    ports_by_id: Mapping[int, PortValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    links_by_id: Mapping[int, LinkValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    metadata_by_id: Mapping[int, MetadataValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    parameters_by_key: Mapping[tuple[str, int, str], ParameterValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    profiles_by_key: Mapping[tuple[int, int], ProfileValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )
    routes_by_key: Mapping[tuple[int, int], RouteValue] = field(
        init=False, repr=False, compare=False, hash=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        _identifier(self.generation, "generation")
        _identifier(self.sequence, "sequence")
        object.__setattr__(self, "captured_at", _timestamp(self.captured_at))
        if not isinstance(self.health, ConnectionHealthValue):
            raise TypeError("health must be a ConnectionHealthValue")
        if self.health.generation != self.generation:
            raise ValueError("health generation must match snapshot generation")

        collection_types: tuple[tuple[str, type[RuntimeValue]], ...] = (
            ("devices", DeviceValue),
            ("nodes", NodeValue),
            ("ports", PortValue),
            ("links", LinkValue),
            ("metadata", MetadataValue),
            ("parameters", ParameterValue),
            ("profiles", ProfileValue),
            ("routes", RouteValue),
        )
        for name, value_type in collection_types:
            object.__setattr__(self, name, _runtime_values(getattr(self, name), value_type, name))
        if not isinstance(self.defaults, DefaultsValue):
            raise TypeError("defaults must be a DefaultsValue")

        supplied_unresolved = _runtime_values(
            self.unresolved_relationships,
            UnresolvedRelationshipValue,
            "unresolved_relationships",
        )

        devices_by_id = _unique_index(self.devices, lambda value: value.id, "device id")
        nodes_by_id = _unique_index(self.nodes, lambda value: value.id, "node id")
        ports_by_id = _unique_index(self.ports, lambda value: value.id, "port id")
        links_by_id = _unique_index(self.links, lambda value: value.id, "link id")
        metadata_by_id = _unique_index(self.metadata, lambda value: value.id, "metadata id")
        parameters_by_key = _unique_index(
            self.parameters,
            lambda value: (value.owner_type, value.owner_id, value.id),
            "parameter key",
        )
        profiles_by_key = _unique_index(
            self.profiles,
            lambda value: (value.device_id, value.index),
            "profile key",
        )
        routes_by_key = _unique_index(
            self.routes,
            lambda value: (value.device_id, value.index),
            "route key",
        )

        indexes = (
            ("devices_by_id", devices_by_id),
            ("nodes_by_id", nodes_by_id),
            ("ports_by_id", ports_by_id),
            ("links_by_id", links_by_id),
            ("metadata_by_id", metadata_by_id),
            ("parameters_by_key", parameters_by_key),
            ("profiles_by_key", profiles_by_key),
            ("routes_by_key", routes_by_key),
        )
        for name, index in indexes:
            object.__setattr__(self, name, MappingProxyType(index))

        computed_unresolved = self._find_unresolved_relationships()
        if supplied_unresolved and supplied_unresolved != computed_unresolved:
            raise ValueError("serialized unresolved relationships do not match snapshot contents")
        object.__setattr__(self, "unresolved_relationships", computed_unresolved)

    @classmethod
    def capture(
        cls,
        *,
        generation: int,
        sequence: int,
        health: ConnectionHealthValue,
        captured_at: datetime | str | None = None,
        **values: object,
    ) -> Self:
        """Create a snapshot, using the current UTC time when none is supplied."""

        timestamp = captured_at or datetime.now(timezone.utc)
        return cls(
            generation=generation,
            sequence=sequence,
            captured_at=_timestamp(timestamp),
            health=health,
            **values,
        )

    @property
    def is_coherent(self) -> bool:
        """Whether every relationship resolves inside this snapshot."""

        return not self.unresolved_relationships

    def _find_unresolved_relationships(self) -> tuple[UnresolvedRelationshipValue, ...]:
        unresolved: list[UnresolvedRelationshipValue] = []

        def missing(
            source_type: str,
            source_id: int | str,
            relation: str,
            target_type: str,
            target_id: int | str,
            reason: str = "target is absent from this snapshot",
        ) -> None:
            unresolved.append(
                UnresolvedRelationshipValue(
                    source_type=source_type,
                    source_id=source_id,
                    relation=relation,
                    target_type=target_type,
                    target_id=target_id,
                    reason=reason,
                )
            )

        for device in self.devices:
            for parameter_id in device.parameter_ids:
                if ("device", device.id, parameter_id) not in self.parameters_by_key:
                    missing("device", device.id, "parameter", "parameter", parameter_id)
            for profile_id in device.profile_ids:
                if (device.id, profile_id) not in self.profiles_by_key:
                    missing("device", device.id, "profile", "profile", profile_id)
            for route_id in device.route_ids:
                if (device.id, route_id) not in self.routes_by_key:
                    missing("device", device.id, "route", "route", route_id)

        for node in self.nodes:
            if node.device_id is not None and node.device_id not in self.devices_by_id:
                missing("node", node.id, "device", "device", node.device_id)
            for parameter_id in node.parameter_ids:
                if ("node", node.id, parameter_id) not in self.parameters_by_key:
                    missing("node", node.id, "parameter", "parameter", parameter_id)
            for port_id, direction, relation in (
                *((port_id, PortDirection.INPUT, "input_port") for port_id in node.input_port_ids),
                *((port_id, PortDirection.OUTPUT, "output_port") for port_id in node.output_port_ids),
            ):
                port = self.ports_by_id.get(port_id)
                if port is None:
                    missing("node", node.id, relation, "port", port_id)
                elif port.node_id != node.id or port.direction is not direction:
                    missing(
                        "node",
                        node.id,
                        relation,
                        "port",
                        port_id,
                        "port ownership or direction does not match the relationship",
                    )

        for port in self.ports:
            if port.node_id not in self.nodes_by_id:
                missing("port", port.id, "node", "node", port.node_id)
            for parameter_id in port.parameter_ids:
                if ("port", port.id, parameter_id) not in self.parameters_by_key:
                    missing("port", port.id, "parameter", "parameter", parameter_id)

        for link in self.links:
            endpoint_relationships = (
                ("output_node", "node", link.output_node_id, self.nodes_by_id),
                ("input_node", "node", link.input_node_id, self.nodes_by_id),
                ("output_port", "port", link.output_port_id, self.ports_by_id),
                ("input_port", "port", link.input_port_id, self.ports_by_id),
            )
            for relation, target_type, target_id, index in endpoint_relationships:
                if target_id not in index:
                    missing("link", link.id, relation, target_type, target_id)
            output_port = self.ports_by_id.get(link.output_port_id)
            if output_port is not None and (
                output_port.node_id != link.output_node_id
                or output_port.direction is not PortDirection.OUTPUT
            ):
                missing(
                    "link",
                    link.id,
                    "output_endpoint",
                    "port",
                    link.output_port_id,
                    "output port does not belong to the output node or has the wrong direction",
                )
            input_port = self.ports_by_id.get(link.input_port_id)
            if input_port is not None and (
                input_port.node_id != link.input_node_id
                or input_port.direction is not PortDirection.INPUT
            ):
                missing(
                    "link",
                    link.id,
                    "input_endpoint",
                    "port",
                    link.input_port_id,
                    "input port does not belong to the input node or has the wrong direction",
                )

        for profile in self.profiles:
            if profile.device_id not in self.devices_by_id:
                missing("profile", profile.index, "device", "device", profile.device_id)

        for route in self.routes:
            if route.device_id not in self.devices_by_id:
                missing("route", route.index, "device", "device", route.device_id)
            for profile_id in route.profile_ids:
                if (route.device_id, profile_id) not in self.profiles_by_key:
                    missing("route", route.index, "profile", "profile", profile_id)

        owner_indexes: dict[str, Mapping[int, RuntimeValue]] = {
            "device": self.devices_by_id,
            "node": self.nodes_by_id,
            "port": self.ports_by_id,
            "link": self.links_by_id,
            "metadata": self.metadata_by_id,
        }
        for parameter in self.parameters:
            owner_index = owner_indexes.get(parameter.owner_type)
            if owner_index is None:
                missing(
                    "parameter",
                    f"{parameter.owner_type}:{parameter.owner_id}:{parameter.id}",
                    "owner",
                    parameter.owner_type,
                    parameter.owner_id,
                    "owner type is unsupported by this snapshot contract",
                )
            elif parameter.owner_id not in owner_index:
                missing(
                    "parameter",
                    f"{parameter.owner_type}:{parameter.owner_id}:{parameter.id}",
                    "owner",
                    parameter.owner_type,
                    parameter.owner_id,
                )

        for name in ("audio_sink", "audio_source", "video_source"):
            target = getattr(self.defaults, name)
            if target is not None and target.resolved_node_id is not None:
                if target.resolved_node_id not in self.nodes_by_id:
                    missing("defaults", name, "resolved_node", "node", target.resolved_node_id)
        if (
            self.defaults.metadata_id is not None
            and self.defaults.metadata_id not in self.metadata_by_id
        ):
            missing(
                "defaults",
                "defaults",
                "metadata",
                "metadata",
                self.defaults.metadata_id,
            )

        return tuple(unresolved)


def runtime_value_from_dict(value: Mapping[str, object]) -> RuntimeValue:
    """Restore any registered runtime value from a serialized envelope."""

    if not isinstance(value, Mapping):
        raise RuntimeValueDecodeError("invalid_envelope", "runtime value must be an object")

    schema_version = value.get("schema_version")
    if schema_version != RUNTIME_VALUE_SCHEMA_VERSION or isinstance(schema_version, bool):
        raise RuntimeValueDecodeError(
            "unsupported_schema_version",
            f"expected {RUNTIME_VALUE_SCHEMA_VERSION}, received {schema_version!r}",
            path="$.schema_version",
        )

    value_type = value.get("value_type")
    if not isinstance(value_type, str) or value_type not in _VALUE_TYPES:
        raise RuntimeValueDecodeError(
            "unsupported_value_type",
            f"unknown runtime value type {value_type!r}",
            path="$.value_type",
        )

    value_class = _VALUE_TYPES[value_type]
    field_names = {
        item.name for item in fields(value_class) if item.metadata.get("serialize", True)
    }
    supplied_names = set(value) - {"schema_version", "value_type"}
    unknown_names = supplied_names - field_names
    if unknown_names:
        names = ", ".join(sorted(unknown_names))
        raise RuntimeValueDecodeError("unknown_fields", f"unknown field(s): {names}")

    payload = {
        name: _deserialize(value[name], path=f"$.{name}")
        for name in supplied_names
    }
    try:
        return value_class(**payload)
    except RuntimeValueDecodeError:
        raise
    except (TypeError, ValueError) as error:
        raise RuntimeValueDecodeError("invalid_value", str(error)) from error


def _serialize(value: object) -> object:
    if isinstance(value, RuntimeValue):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, FrozenDict):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"cannot serialize runtime field of type {type(value).__name__!r}")


def _deserialize(value: object, *, path: str) -> object:
    if isinstance(value, Mapping):
        if "schema_version" in value and "value_type" in value:
            try:
                return runtime_value_from_dict(value)
            except RuntimeValueDecodeError as error:
                raise RuntimeValueDecodeError(error.code, error.message, path=path) from error
        try:
            return FrozenDict({key: _deserialize(item, path=f"{path}.{key}") for key, item in value.items()})
        except (TypeError, ValueError) as error:
            raise RuntimeValueDecodeError("invalid_json_value", str(error), path=path) from error
    if isinstance(value, list):
        return tuple(_deserialize(item, path=f"{path}[{index}]") for index, item in enumerate(value))
    try:
        return freeze_json(value)
    except (TypeError, ValueError) as error:
        raise RuntimeValueDecodeError("invalid_json_value", str(error), path=path) from error


def _mapping(value: object, name: str) -> FrozenDict:
    if isinstance(value, FrozenDict):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return FrozenDict(value)


def _contract_value(value: object) -> object:
    if isinstance(value, RuntimeValue):
        return value
    return freeze_json(value)


def _unique_index(values: Sequence[object], key: object, name: str) -> dict[object, object]:
    result: dict[object, object] = {}
    for value in values:
        item_key = key(value)
        if item_key in result:
            raise ValueError(f"duplicate {name}: {item_key!r}")
        result[item_key] = value
    return result


def _runtime_values(value: object, expected: type[RuntimeValue], name: str) -> tuple[RuntimeValue, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence")
    result = tuple(value)
    if not all(isinstance(item, expected) for item in result):
        raise TypeError(f"every {name} item must be {expected.__name__}")
    return result


def _enum(enum_type: type[Enum], value: object, name: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} has invalid value {value!r}") from error


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _identifier(value: object, name: str) -> int:
    result = _integer(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _identity(value: object, name: str) -> int | str:
    if isinstance(value, str):
        return _required_string(value, name)
    return _identifier(value, name)


def _optional_identifier(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _identifier(value, name)


def _identifiers(value: object, name: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence")
    return tuple(_identifier(item, f"{name} item") for item in value)


def _required_string(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, name, allow_empty=True)


def _optional_strings(instance: object, *names: str) -> None:
    for name in names:
        _optional_string(getattr(instance, name), name)


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence")
    return tuple(_required_string(item, f"{name} item") for item in value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _optional_boolean(value: object, name: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, name)


def _optional_float(value: object, name: str) -> float | None:
    if value is None:
        return None
    return _float(value, name)


def _float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    freeze_json(result)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _floats(value: object, name: str) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be a sequence")
    return tuple(_float(item, f"{name} item") for item in value)


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("captured_at must be an ISO 8601 timestamp") from error
    else:
        raise TypeError("captured_at must be a datetime or ISO 8601 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("captured_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
