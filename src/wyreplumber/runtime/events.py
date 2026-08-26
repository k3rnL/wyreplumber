"""Detached ordered events for incrementally updating a runtime projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from .normalize import normalize_spa_json
from .models import (
    RuntimeValue,
    _contract_value,
    _identifier,
    _identity,
    _optional_string,
    _required_string,
    _timestamp,
)


NATIVE_RUNTIME_EVENT_PAYLOAD_VERSION = 1

_REQUIRED_NATIVE_EVENT_FIELDS = {
    "payload_version",
    "generation",
    "sequence",
    "occurred_at",
    "kind",
    "object_kind",
    "object_id",
    "current",
    "previous",
    "requires_resnapshot",
    "reason",
}


class RuntimeEventKind(str, Enum):
    OBJECT_ADDED = "object_added"
    OBJECT_REMOVED = "object_removed"
    OBJECT_CHANGED = "object_changed"
    PARAMETER_CHANGED = "parameter_changed"
    METADATA_CHANGED = "metadata_changed"
    DEFAULT_CHANGED = "default_changed"
    CONNECTION_CHANGED = "connection_changed"
    DISCONTINUITY = "discontinuity"
    RESNAPSHOT_REQUIRED = "resnapshot_required"


class RuntimeObjectKind(str, Enum):
    DEVICE = "device"
    NODE = "node"
    PORT = "port"
    LINK = "link"
    METADATA = "metadata"
    PARAMETER = "parameter"
    PROFILE = "profile"
    ROUTE = "route"
    DEFAULTS = "defaults"
    CONNECTION = "connection"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class RuntimeEvent(RuntimeValue):
    """One detached state transition within a connection generation."""

    VALUE_TYPE: ClassVar[str] = "runtime_event"

    generation: int
    sequence: int
    occurred_at: str
    kind: RuntimeEventKind
    object_kind: RuntimeObjectKind
    object_id: int | str
    current: object = None
    previous: object = None
    requires_resnapshot: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.generation, "generation")
        _identifier(self.sequence, "sequence")
        object.__setattr__(self, "occurred_at", _timestamp(self.occurred_at))
        try:
            object.__setattr__(self, "kind", RuntimeEventKind(self.kind))
        except (TypeError, ValueError) as error:
            raise ValueError(f"kind has invalid value {self.kind!r}") from error
        try:
            object.__setattr__(self, "object_kind", RuntimeObjectKind(self.object_kind))
        except (TypeError, ValueError) as error:
            raise ValueError(f"object_kind has invalid value {self.object_kind!r}") from error
        _identity(self.object_id, "object_id")
        object.__setattr__(self, "current", _contract_value(self.current))
        object.__setattr__(self, "previous", _contract_value(self.previous))
        if not isinstance(self.requires_resnapshot, bool):
            raise TypeError("requires_resnapshot must be a boolean")
        _optional_string(self.reason, "reason")

        if self.kind in {
            RuntimeEventKind.DISCONTINUITY,
            RuntimeEventKind.RESNAPSHOT_REQUIRED,
        } and not self.requires_resnapshot:
            raise ValueError(f"{self.kind.value} must require a new snapshot")
        if self.kind is RuntimeEventKind.OBJECT_ADDED and self.current is None:
            raise ValueError("object_added must include current state")
        if self.kind is RuntimeEventKind.OBJECT_REMOVED and self.previous is None:
            raise ValueError("object_removed must include previous state")

    @classmethod
    def discontinuity(
        cls,
        *,
        generation: int,
        sequence: int,
        occurred_at: str,
        reason: str,
    ) -> "RuntimeEvent":
        return cls(
            generation=generation,
            sequence=sequence,
            occurred_at=occurred_at,
            kind=RuntimeEventKind.DISCONTINUITY,
            object_kind=RuntimeObjectKind.RUNTIME,
            object_id="runtime",
            requires_resnapshot=True,
            reason=_required_string(reason, "reason"),
        )


class RuntimeContinuityError(RuntimeError):
    """An event cannot be applied to the caller's current projection."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        expected_generation: int,
        expected_sequence: int,
        event: RuntimeEvent,
    ) -> None:
        self.code = code
        self.expected_generation = expected_generation
        self.expected_sequence = expected_sequence
        self.event = event
        super().__init__(message)


def require_event_continuity(
    event: RuntimeEvent,
    *,
    generation: int,
    sequence: int,
) -> RuntimeEvent:
    """Validate that an event immediately follows an existing projection."""

    _identifier(generation, "generation")
    _identifier(sequence, "sequence")
    if event.generation != generation:
        raise RuntimeContinuityError(
            "generation_changed",
            f"event generation {event.generation} does not match projection {generation}",
            expected_generation=generation,
            expected_sequence=sequence + 1,
            event=event,
        )
    if event.sequence != sequence + 1:
        raise RuntimeContinuityError(
            "sequence_gap",
            f"expected event sequence {sequence + 1}, received {event.sequence}",
            expected_generation=generation,
            expected_sequence=sequence + 1,
            event=event,
        )
    if event.requires_resnapshot:
        raise RuntimeContinuityError(
            "resnapshot_required",
            event.reason or "event invalidates incremental continuity",
            expected_generation=generation,
            expected_sequence=sequence + 1,
            event=event,
        )
    return event


def runtime_event_from_payload(payload: Mapping[str, object]) -> RuntimeEvent:
    """Validate and normalize one detached native event payload."""

    # Imported lazily to keep the value model independent of native payload code.
    from .snapshot import (
        RuntimePayloadError,
        _devices,
        _health,
        _links,
        _mapping,
        _metadata,
        _nodes,
        _parameters,
        _ports,
        _validate_detached,
    )

    if not isinstance(payload, Mapping):
        raise RuntimePayloadError("invalid_event_payload", "payload must be a mapping")
    _validate_detached(payload)
    missing = _REQUIRED_NATIVE_EVENT_FIELDS - set(payload)
    unknown = set(payload) - _REQUIRED_NATIVE_EVENT_FIELDS
    if missing:
        raise RuntimePayloadError(
            "missing_fields",
            f"missing event payload field(s): {', '.join(sorted(missing))}",
        )
    if unknown:
        raise RuntimePayloadError(
            "unknown_fields",
            f"unknown event payload field(s): {', '.join(sorted(unknown))}",
        )
    version = payload["payload_version"]
    if version != NATIVE_RUNTIME_EVENT_PAYLOAD_VERSION or isinstance(version, bool):
        raise RuntimePayloadError(
            "unsupported_event_payload_version",
            f"expected {NATIVE_RUNTIME_EVENT_PAYLOAD_VERSION}, received {version!r}",
            path="$.payload_version",
        )

    try:
        kind = RuntimeEventKind(payload["kind"])
        object_kind = RuntimeObjectKind(payload["object_kind"])
    except (TypeError, ValueError) as error:
        raise RuntimePayloadError("invalid_event_kind", str(error)) from error

    generation = _identifier(payload["generation"], "generation")
    sequence = _identifier(payload["sequence"], "sequence")

    def state(value: object) -> object:
        if value is None:
            return None
        record = _mapping(value, "$.event_state")
        try:
            if kind in {
                RuntimeEventKind.OBJECT_ADDED,
                RuntimeEventKind.OBJECT_REMOVED,
                RuntimeEventKind.OBJECT_CHANGED,
            }:
                if object_kind is RuntimeObjectKind.DEVICE:
                    return _devices((record,), profiles_by_key={}, routes_by_key={})[0]
                if object_kind is RuntimeObjectKind.NODE:
                    return _nodes((record,), {}, {})[0]
                if object_kind is RuntimeObjectKind.PORT:
                    return _ports((record,))[0]
                if object_kind is RuntimeObjectKind.LINK:
                    return _links((record,))[0]
                if object_kind is RuntimeObjectKind.METADATA:
                    return _metadata((record,))[0]
            if object_kind is RuntimeObjectKind.PARAMETER:
                return _parameters((record,))[0]
            if object_kind is RuntimeObjectKind.CONNECTION:
                return _health(record, generation)
        except (RuntimePayloadError, IndexError):
            # Removal can arrive after a proxy has already lost features. The raw
            # primitive record is still a stable detached diagnostic value. Raw
            # parameter records can contain copied SPA POD bytes, so normalize
            # them before the immutable JSON contract validates the event.
            return normalize_spa_json(record)
        return normalize_spa_json(record)

    reason = payload["reason"]
    if reason is not None and not isinstance(reason, str):
        raise RuntimePayloadError("invalid_event_reason", "reason must be a string or null")
    requires_resnapshot = payload["requires_resnapshot"]
    if not isinstance(requires_resnapshot, bool):
        raise RuntimePayloadError(
            "invalid_resnapshot_flag",
            "requires_resnapshot must be a boolean",
        )
    try:
        return RuntimeEvent(
            generation=generation,
            sequence=sequence,
            occurred_at=payload["occurred_at"],
            kind=kind,
            object_kind=object_kind,
            object_id=payload["object_id"],
            current=state(payload["current"]),
            previous=state(payload["previous"]),
            requires_resnapshot=requires_resnapshot,
            reason=reason,
        )
    except (TypeError, ValueError) as error:
        raise RuntimePayloadError("invalid_event", str(error)) from error


def next_runtime_event(
    connection: object,
    *,
    block: bool = True,
    timeout: float | None = None,
) -> RuntimeEvent | None:
    """Read and decode one event from a native connection publication queue."""

    read = getattr(connection, "next_runtime_event_payload", None)
    if not callable(read):
        raise TypeError("connection must provide next_runtime_event_payload()")
    payload = read(block=block, timeout=timeout)
    return None if payload is None else runtime_event_from_payload(payload)


def drain_runtime_events(
    connection: object,
    *,
    max_events: int = 0,
) -> tuple[RuntimeEvent, ...]:
    """Decode all native event payloads currently available without waiting."""

    drain = getattr(connection, "drain_runtime_event_payloads", None)
    if not callable(drain):
        raise TypeError("connection must provide drain_runtime_event_payloads()")
    return tuple(
        runtime_event_from_payload(payload)
        for payload in drain(max_events=max_events)
    )
