"""Detached request and outcome values for managed runtime mutations."""

from __future__ import annotations

import base64
import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite
from time import sleep
from typing import ClassVar
from uuid import uuid4

from ._immutable import FrozenDict, freeze_json
from .events import RuntimeObjectKind
from .models import (
    Availability,
    LinkValue,
    ProfileValue,
    RouteValue,
    RuntimeValue,
    _contract_value,
    _identifier,
    _identity,
    _mapping,
    _optional_identifier,
    _optional_string,
    _required_string,
    _timestamp,
)


class MutationOperation(str, Enum):
    SET_PARAMETER = "set_parameter"
    SET_METADATA = "set_metadata"
    CLEAR_METADATA = "clear_metadata"
    SELECT_PROFILE = "select_profile"
    SELECT_ROUTE = "select_route"
    CREATE_LINK = "create_link"
    REMOVE_LINK = "remove_link"


class ConfirmationOperator(str, Enum):
    EQUALS = "equals"
    PRESENT = "present"
    ABSENT = "absent"


class MutationStatus(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class MutationDispatchDisposition(str, Enum):
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MutationFailurePhase(str, Enum):
    VALIDATION = "validation"
    PRECONDITION = "precondition"
    EXECUTION = "execution"
    CONFIRMATION = "confirmation"
    DEADLINE = "deadline"
    CANCELLATION = "cancellation"


class MutationFailureCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    STALE_GENERATION = "stale_generation"
    STALE_SEQUENCE = "stale_sequence"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_IDENTITY_CHANGED = "target_identity_changed"
    TARGET_UNAVAILABLE = "target_unavailable"
    NOT_WRITABLE = "not_writable"
    OWNERSHIP_CONFLICT = "ownership_conflict"
    NATIVE_REJECTED = "native_rejected"
    CONFIRMATION_TIMEOUT = "confirmation_timeout"
    DEADLINE_EXPIRED = "deadline_expired"
    GENERATION_LOST = "generation_lost"
    RUNTIME_STOPPED = "runtime_stopped"
    CALLER_CANCELLED = "caller_cancelled"
    INTERNAL_ERROR = "internal_error"


_FAILURE_CODES_BY_PHASE = {
    MutationFailurePhase.VALIDATION: {
        MutationFailureCode.INVALID_REQUEST,
        MutationFailureCode.UNSUPPORTED_OPERATION,
    },
    MutationFailurePhase.PRECONDITION: {
        MutationFailureCode.STALE_GENERATION,
        MutationFailureCode.STALE_SEQUENCE,
        MutationFailureCode.TARGET_NOT_FOUND,
        MutationFailureCode.TARGET_IDENTITY_CHANGED,
        MutationFailureCode.TARGET_UNAVAILABLE,
        MutationFailureCode.NOT_WRITABLE,
        MutationFailureCode.OWNERSHIP_CONFLICT,
    },
    MutationFailurePhase.EXECUTION: {
        MutationFailureCode.NATIVE_REJECTED,
        MutationFailureCode.INTERNAL_ERROR,
    },
    MutationFailurePhase.CONFIRMATION: {
        MutationFailureCode.CONFIRMATION_TIMEOUT,
    },
    MutationFailurePhase.DEADLINE: {
        MutationFailureCode.DEADLINE_EXPIRED,
    },
    MutationFailurePhase.CANCELLATION: {
        MutationFailureCode.GENERATION_LOST,
        MutationFailureCode.RUNTIME_STOPPED,
        MutationFailureCode.CALLER_CANCELLED,
    },
}


@dataclass(frozen=True, slots=True)
class MutationTargetValue(RuntimeValue):
    """Generation-scoped target identity plus an optional subresource selector."""

    VALUE_TYPE: ClassVar[str] = "mutation_target"

    object_kind: RuntimeObjectKind
    object_id: int | str
    selector: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "object_kind", RuntimeObjectKind(self.object_kind))
        except (TypeError, ValueError) as error:
            raise ValueError(f"object_kind has invalid value {self.object_kind!r}") from error
        if self.object_kind in {RuntimeObjectKind.CONNECTION, RuntimeObjectKind.RUNTIME}:
            raise ValueError(f"{self.object_kind.value} is not a mutable runtime target")
        _identity(self.object_id, "object_id")
        object.__setattr__(self, "selector", _mapping(self.selector, "selector"))


@dataclass(frozen=True, slots=True)
class ConfirmationPredicateValue(RuntimeValue):
    """Declarative condition that an observed detached value can evaluate."""

    VALUE_TYPE: ClassVar[str] = "confirmation_predicate"

    target: MutationTargetValue
    operator: ConfirmationOperator
    path: tuple[str | int, ...] = ()
    expected: object = None

    def __post_init__(self) -> None:
        if not isinstance(self.target, MutationTargetValue):
            raise TypeError("target must be a MutationTargetValue")
        try:
            object.__setattr__(self, "operator", ConfirmationOperator(self.operator))
        except (TypeError, ValueError) as error:
            raise ValueError(f"operator has invalid value {self.operator!r}") from error
        if not isinstance(self.path, Sequence) or isinstance(
            self.path, (str, bytes, bytearray)
        ):
            raise TypeError("path must be a sequence of field names and indexes")
        normalized_path: list[str | int] = []
        for component in self.path:
            if isinstance(component, str):
                normalized_path.append(_required_string(component, "path component"))
            else:
                normalized_path.append(_identifier(component, "path component"))
        object.__setattr__(self, "path", tuple(normalized_path))
        object.__setattr__(self, "expected", _contract_value(self.expected))
        if self.operator in {ConfirmationOperator.PRESENT, ConfirmationOperator.ABSENT}:
            if self.expected is not None:
                raise ValueError(f"{self.operator.value} predicates must not set expected")

    def matches(self, observation: object) -> bool:
        """Evaluate this predicate against one detached observation."""

        value = observation.to_dict() if isinstance(observation, RuntimeValue) else observation
        found, value = _resolve_path(value, self.path)
        if self.operator is ConfirmationOperator.PRESENT:
            return found and value is not None
        if self.operator is ConfirmationOperator.ABSENT:
            return not found or value is None
        if not found:
            return False
        return _comparable(value) == _comparable(self.expected)


@dataclass(frozen=True, slots=True)
class MutationRequest(RuntimeValue):
    """One validated, generation-scoped mutation submitted to a dispatcher."""

    VALUE_TYPE: ClassVar[str] = "mutation_request"

    request_id: str
    expected_generation: int
    operation: MutationOperation
    target: MutationTargetValue
    requested_at: str
    deadline_at: str
    expected_sequence: int | None = None
    payload: FrozenDict = field(default_factory=FrozenDict)
    confirmation_predicates: tuple[ConfirmationPredicateValue, ...] = ()

    def __post_init__(self) -> None:
        _required_string(self.request_id, "request_id")
        _identifier(self.expected_generation, "expected_generation")
        _optional_identifier(self.expected_sequence, "expected_sequence")
        try:
            object.__setattr__(self, "operation", MutationOperation(self.operation))
        except (TypeError, ValueError) as error:
            raise ValueError(f"operation has invalid value {self.operation!r}") from error
        if not isinstance(self.target, MutationTargetValue):
            raise TypeError("target must be a MutationTargetValue")
        object.__setattr__(self, "requested_at", _named_timestamp(self.requested_at, "requested_at"))
        object.__setattr__(self, "deadline_at", _named_timestamp(self.deadline_at, "deadline_at"))
        if _parse_timestamp(self.deadline_at) < _parse_timestamp(self.requested_at):
            raise ValueError("deadline_at must not precede requested_at")
        object.__setattr__(self, "payload", _mapping(self.payload, "payload"))
        if not isinstance(self.confirmation_predicates, Sequence) or isinstance(
            self.confirmation_predicates, (str, bytes, bytearray)
        ):
            raise TypeError("confirmation_predicates must be a sequence")
        predicates = tuple(self.confirmation_predicates)
        if not predicates:
            raise ValueError("confirmation_predicates must contain at least one predicate")
        if not all(isinstance(item, ConfirmationPredicateValue) for item in predicates):
            raise TypeError(
                "every confirmation_predicates item must be ConfirmationPredicateValue"
            )
        object.__setattr__(self, "confirmation_predicates", predicates)

    @classmethod
    def create(
        cls,
        *,
        expected_generation: int,
        operation: MutationOperation,
        target: MutationTargetValue,
        confirmation_predicates: Sequence[ConfirmationPredicateValue],
        timeout: float = 5.0,
        expected_sequence: int | None = None,
        payload: Mapping[str, object] | None = None,
        request_id: str | None = None,
        now: datetime | str | None = None,
    ) -> "MutationRequest":
        """Create a request with a unique identity and absolute UTC deadline."""

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a number")
        timeout_value = float(timeout)
        if not isfinite(timeout_value) or timeout_value < 0:
            raise ValueError("timeout must be finite and non-negative")
        requested = _parse_timestamp(now or datetime.now(timezone.utc))
        deadline = requested + timedelta(seconds=timeout_value)
        return cls(
            request_id=request_id or str(uuid4()),
            expected_generation=expected_generation,
            expected_sequence=expected_sequence,
            operation=operation,
            target=target,
            requested_at=requested,
            deadline_at=deadline,
            payload=payload or {},
            confirmation_predicates=tuple(confirmation_predicates),
        )

    def is_expired(self, at: datetime | str | None = None) -> bool:
        """Return whether the absolute deadline has been reached."""

        observed = _parse_timestamp(at or datetime.now(timezone.utc))
        return observed >= _parse_timestamp(self.deadline_at)


@dataclass(frozen=True, slots=True)
class MutationFailureValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "mutation_failure"

    phase: MutationFailurePhase
    code: MutationFailureCode
    message: str
    retryable: bool = False
    details: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "phase", MutationFailurePhase(self.phase))
            object.__setattr__(self, "code", MutationFailureCode(self.code))
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid mutation failure classification: {error}") from error
        if self.code not in _FAILURE_CODES_BY_PHASE[self.phase]:
            raise ValueError(
                f"failure code {self.code.value!r} is invalid for phase {self.phase.value!r}"
            )
        _required_string(self.message, "message")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")
        object.__setattr__(self, "details", _mapping(self.details, "details"))


@dataclass(frozen=True, slots=True)
class MutationConfirmationValue(RuntimeValue):
    VALUE_TYPE: ClassVar[str] = "mutation_confirmation"

    generation: int
    sequence: int
    observed_at: str
    predicate: ConfirmationPredicateValue
    observation: object

    def __post_init__(self) -> None:
        _identifier(self.generation, "generation")
        _identifier(self.sequence, "sequence")
        object.__setattr__(self, "observed_at", _named_timestamp(self.observed_at, "observed_at"))
        if not isinstance(self.predicate, ConfirmationPredicateValue):
            raise TypeError("predicate must be a ConfirmationPredicateValue")
        object.__setattr__(self, "observation", _contract_value(self.observation))
        if not self.predicate.matches(self.observation):
            raise ValueError("observation does not satisfy the confirmation predicate")


@dataclass(frozen=True, slots=True)
class MutationOutcome(RuntimeValue):
    """Terminal structured result of one mutation request."""

    VALUE_TYPE: ClassVar[str] = "mutation_outcome"

    request_id: str
    generation: int
    operation: MutationOperation
    status: MutationStatus
    completed_at: str
    confirmations: tuple[MutationConfirmationValue, ...] = ()
    failure: MutationFailureValue | None = None

    def __post_init__(self) -> None:
        _required_string(self.request_id, "request_id")
        _identifier(self.generation, "generation")
        try:
            object.__setattr__(self, "operation", MutationOperation(self.operation))
            object.__setattr__(self, "status", MutationStatus(self.status))
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid mutation outcome classification: {error}") from error
        object.__setattr__(self, "completed_at", _named_timestamp(self.completed_at, "completed_at"))
        if not isinstance(self.confirmations, Sequence) or isinstance(
            self.confirmations, (str, bytes, bytearray)
        ):
            raise TypeError("confirmations must be a sequence")
        confirmations = tuple(self.confirmations)
        if not all(isinstance(item, MutationConfirmationValue) for item in confirmations):
            raise TypeError("every confirmations item must be MutationConfirmationValue")
        if any(item.generation != self.generation for item in confirmations):
            raise ValueError("confirmation generation must match outcome generation")
        object.__setattr__(self, "confirmations", confirmations)
        if self.failure is not None and not isinstance(self.failure, MutationFailureValue):
            raise TypeError("failure must be a MutationFailureValue or None")

        if self.status is MutationStatus.CONFIRMED:
            if self.failure is not None:
                raise ValueError("confirmed outcomes must not include a failure")
            if not confirmations:
                raise ValueError("confirmed outcomes must include confirming observations")
        elif self.failure is None:
            raise ValueError("unsuccessful outcomes must include a structured failure")

        if self.status is not MutationStatus.CONFIRMED:
            codes_by_status = {
                MutationStatus.REJECTED: {
                    *(_FAILURE_CODES_BY_PHASE[MutationFailurePhase.VALIDATION]),
                    *(_FAILURE_CODES_BY_PHASE[MutationFailurePhase.PRECONDITION]),
                },
                MutationStatus.FAILED: _FAILURE_CODES_BY_PHASE[
                    MutationFailurePhase.EXECUTION
                ],
                MutationStatus.TIMED_OUT: {
                    MutationFailureCode.CONFIRMATION_TIMEOUT,
                    MutationFailureCode.DEADLINE_EXPIRED,
                },
                MutationStatus.CANCELLED: _FAILURE_CODES_BY_PHASE[
                    MutationFailurePhase.CANCELLATION
                ],
            }
            if self.failure.code not in codes_by_status[self.status]:
                raise ValueError(
                    f"{self.status.value} outcome has incompatible failure code "
                    f"{self.failure.code.value!r}"
                )

    @property
    def succeeded(self) -> bool:
        return self.status is MutationStatus.CONFIRMED


@dataclass(frozen=True, slots=True)
class MutationDispatchTicketValue(RuntimeValue):
    """Native FIFO/precondition result immediately before operation execution."""

    VALUE_TYPE: ClassVar[str] = "mutation_dispatch_ticket"

    request_id: str
    operation: MutationOperation
    dispatch_order: int
    disposition: MutationDispatchDisposition
    expected_generation: int
    observed_generation: int
    observed_sequence: int
    expected_sequence: int | None = None
    failure_code: MutationFailureCode | None = None

    def __post_init__(self) -> None:
        _required_string(self.request_id, "request_id")
        try:
            object.__setattr__(self, "operation", MutationOperation(self.operation))
            object.__setattr__(
                self, "disposition", MutationDispatchDisposition(self.disposition)
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid mutation dispatch classification: {error}") from error
        _identifier(self.dispatch_order, "dispatch_order")
        _identifier(self.expected_generation, "expected_generation")
        _optional_identifier(self.expected_sequence, "expected_sequence")
        _identifier(self.observed_generation, "observed_generation")
        _identifier(self.observed_sequence, "observed_sequence")
        if self.failure_code is not None:
            try:
                object.__setattr__(
                    self, "failure_code", MutationFailureCode(self.failure_code)
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"failure_code has invalid value {self.failure_code!r}") from error

        if self.disposition is MutationDispatchDisposition.READY:
            if self.failure_code is not None:
                raise ValueError("ready dispatch tickets must not include a failure code")
            if self.dispatch_order == 0:
                raise ValueError("ready dispatch tickets must have a positive dispatch order")
        elif self.failure_code is None:
            raise ValueError("non-ready dispatch tickets must include a failure code")

        if self.disposition is MutationDispatchDisposition.REJECTED and self.failure_code not in {
            MutationFailureCode.UNSUPPORTED_OPERATION,
            MutationFailureCode.STALE_GENERATION,
            MutationFailureCode.STALE_SEQUENCE,
            MutationFailureCode.TARGET_NOT_FOUND,
            MutationFailureCode.TARGET_IDENTITY_CHANGED,
            MutationFailureCode.TARGET_UNAVAILABLE,
            MutationFailureCode.NOT_WRITABLE,
            MutationFailureCode.OWNERSHIP_CONFLICT,
        }:
            raise ValueError("rejected dispatch tickets require a validation or precondition code")
        if self.disposition is MutationDispatchDisposition.FAILED and self.failure_code not in {
            MutationFailureCode.NATIVE_REJECTED,
            MutationFailureCode.INTERNAL_ERROR,
        }:
            raise ValueError("failed dispatch tickets require an execution failure code")
        if self.disposition is MutationDispatchDisposition.CANCELLED and self.failure_code not in {
            MutationFailureCode.GENERATION_LOST,
            MutationFailureCode.RUNTIME_STOPPED,
        }:
            raise ValueError("cancelled dispatch tickets require a lifecycle cancellation code")


NATIVE_MUTATION_DISPATCH_PAYLOAD_VERSION = 1


def dispatch_runtime_mutation(
    connection: object, request: MutationRequest
) -> MutationDispatchTicketValue:
    """Enter the connection FIFO and validate preconditions on its WP context."""

    if not isinstance(request, MutationRequest):
        raise TypeError("request must be a MutationRequest")
    dispatch = getattr(connection, "dispatch_runtime_mutation_payload", None)
    if not callable(dispatch):
        raise TypeError("connection must provide dispatch_runtime_mutation_payload()")
    return mutation_dispatch_ticket_from_payload(dispatch(request.to_dict()))


def mutation_dispatch_ticket_from_payload(
    payload: Mapping[str, object],
) -> MutationDispatchTicketValue:
    """Validate one primitive payload returned by the native FIFO boundary."""

    required = {
        "payload_version",
        "request_id",
        "operation",
        "dispatch_order",
        "disposition",
        "expected_generation",
        "expected_sequence",
        "observed_generation",
        "observed_sequence",
        "failure_code",
    }
    if not isinstance(payload, Mapping):
        raise TypeError("native mutation dispatch payload must be a mapping")
    missing = required - set(payload)
    unknown = set(payload) - required
    if missing:
        raise ValueError(
            f"native mutation dispatch payload is missing: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise ValueError(
            f"native mutation dispatch payload has unknown fields: "
            f"{', '.join(sorted(unknown))}"
        )
    if payload["payload_version"] != NATIVE_MUTATION_DISPATCH_PAYLOAD_VERSION or isinstance(
        payload["payload_version"], bool
    ):
        raise ValueError(
            "unsupported native mutation dispatch payload version "
            f"{payload['payload_version']!r}"
        )
    return MutationDispatchTicketValue(
        request_id=payload["request_id"],
        operation=payload["operation"],
        dispatch_order=payload["dispatch_order"],
        disposition=payload["disposition"],
        expected_generation=payload["expected_generation"],
        expected_sequence=payload["expected_sequence"],
        observed_generation=payload["observed_generation"],
        observed_sequence=payload["observed_sequence"],
        failure_code=payload["failure_code"],
    )


def set_runtime_parameter(
    connection: object,
    *,
    expected_generation: int,
    target_kind: RuntimeObjectKind,
    target_id: int,
    parameter_id: str,
    value: object,
    confirmation_predicates: Sequence[ConfirmationPredicateValue],
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    flags: int = 0,
    pod_type: int | None = None,
    request_id: str | None = None,
) -> MutationOutcome:
    """Set a validated SPA parameter and await detached observed confirmation."""

    try:
        target_kind = RuntimeObjectKind(target_kind)
    except (TypeError, ValueError) as error:
        raise ValueError(f"target_kind has invalid value {target_kind!r}") from error
    if target_kind not in {
        RuntimeObjectKind.DEVICE,
        RuntimeObjectKind.NODE,
        RuntimeObjectKind.PORT,
    }:
        raise ValueError("parameter targets must be a device, node, or port")
    _identifier(target_id, "target_id")
    _required_string(parameter_id, "parameter_id")
    if isinstance(flags, bool) or not isinstance(flags, int):
        raise TypeError("flags must be an integer")
    if flags < 0 or flags > 0xFFFFFFFF:
        raise ValueError("flags must be between 0 and 4294967295")
    predicates = tuple(confirmation_predicates)
    raw_pod = _parameter_pod_bytes(value, pod_type=pod_type)
    target = MutationTargetValue(
        object_kind=target_kind,
        object_id=target_id,
        selector={"parameter_id": parameter_id},
    )
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.SET_PARAMETER,
        target=target,
        payload={
            "flags": flags,
            "pod_base64": base64.b64encode(raw_pod).decode("ascii"),
        },
        confirmation_predicates=predicates,
        timeout=timeout,
    )

    return _execute_confirmed_mutation(connection, request)


def _execute_confirmed_mutation(
    connection: object,
    request: MutationRequest,
    *,
    preflight: object | None = None,
) -> MutationOutcome:
    """Execute one request through the common preflight/dispatch/observe path."""

    predicates = request.confirmation_predicates
    if request.is_expired():
        return _failure_outcome(
            request,
            status=MutationStatus.TIMED_OUT,
            phase=MutationFailurePhase.DEADLINE,
            code=MutationFailureCode.DEADLINE_EXPIRED,
            message="mutation deadline expired before runtime preflight",
        )

    if preflight is None:
        try:
            preflight = _capture_snapshot(connection)
        except RuntimeError as error:
            return _runtime_unavailable_outcome(request, error)
    if preflight.generation != request.expected_generation:
        return _failure_outcome(
            request,
            status=MutationStatus.REJECTED,
            phase=MutationFailurePhase.PRECONDITION,
            code=MutationFailureCode.STALE_GENERATION,
            message=(
                f"expected generation {request.expected_generation}, observed "
                f"{preflight.generation}"
            ),
            details={"observed_generation": preflight.generation},
        )
    if (
        request.expected_sequence is not None
        and preflight.sequence != request.expected_sequence + 1
    ):
        return _failure_outcome(
            request,
            status=MutationStatus.REJECTED,
            phase=MutationFailurePhase.PRECONDITION,
            code=MutationFailureCode.STALE_SEQUENCE,
            message=(
                f"expected projection sequence {request.expected_sequence}, preflight "
                f"captured sequence {preflight.sequence}"
            ),
            details={"observed_sequence": preflight.sequence},
        )

    confirmations = _confirmations_from_snapshot(preflight, predicates)
    if len(confirmations) == len(predicates):
        return MutationOutcome(
            request_id=request.request_id,
            generation=request.expected_generation,
            operation=request.operation,
            status=MutationStatus.CONFIRMED,
            completed_at=preflight.captured_at,
            confirmations=confirmations,
        )
    if request.is_expired():
        return _failure_outcome(
            request,
            status=MutationStatus.TIMED_OUT,
            phase=MutationFailurePhase.DEADLINE,
            code=MutationFailureCode.DEADLINE_EXPIRED,
            message="mutation deadline expired during runtime preflight",
            confirmations=confirmations,
        )

    # The preflight snapshot is now the exact boundary against which native
    # execution validates its optional sequence precondition.
    dispatched_request = (
        replace(request, expected_sequence=preflight.sequence)
        if request.expected_sequence is not None
        else request
    )
    ticket = dispatch_runtime_mutation(connection, dispatched_request)
    if ticket.disposition is not MutationDispatchDisposition.READY:
        return _ticket_failure_outcome(dispatched_request, ticket)

    confirmations = ()
    while True:
        if dispatched_request.is_expired():
            return _failure_outcome(
                dispatched_request,
                status=MutationStatus.TIMED_OUT,
                phase=MutationFailurePhase.CONFIRMATION,
                code=MutationFailureCode.CONFIRMATION_TIMEOUT,
                message="native mutation was accepted but state was not confirmed",
                confirmations=confirmations,
            )
        try:
            snapshot = _capture_snapshot(connection)
        except RuntimeError as error:
            return _runtime_unavailable_outcome(
                dispatched_request,
                error,
                confirmations=confirmations,
            )
        if snapshot.generation != dispatched_request.expected_generation:
            return _failure_outcome(
                dispatched_request,
                status=MutationStatus.CANCELLED,
                phase=MutationFailurePhase.CANCELLATION,
                code=MutationFailureCode.GENERATION_LOST,
                message="connection generation changed before confirmation",
                details={"observed_generation": snapshot.generation},
                confirmations=confirmations,
            )
        confirmations = _confirmations_from_snapshot(snapshot, predicates)
        if len(confirmations) == len(predicates):
            return MutationOutcome(
                request_id=dispatched_request.request_id,
                generation=dispatched_request.expected_generation,
                operation=dispatched_request.operation,
                status=MutationStatus.CONFIRMED,
                completed_at=snapshot.captured_at,
                confirmations=confirmations,
            )
        sleep(0.01)


_UNSET = object()


def set_node_audio_properties(
    connection: object,
    *,
    node_id: int,
    expected_generation: int,
    expected_sequence: int | None = None,
    volume: object = _UNSET,
    mute: object = _UNSET,
    channel_volumes: object = _UNSET,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Set one or more typed node audio properties through ``SPA_PARAM_Props``."""

    from wyreplumber import spa_pod

    if volume is mute is channel_volumes is _UNSET:
        raise ValueError("at least one audio property must be supplied")
    properties: dict[str, object] = {}
    expected: dict[str, object] = {}
    if volume is not _UNSET:
        properties["volume"] = _non_negative_finite(volume, "volume")
        expected["volume"] = _float32(properties["volume"])
    if mute is not _UNSET:
        if not isinstance(mute, bool):
            raise TypeError("mute must be a boolean")
        properties["mute"] = mute
        expected["mute"] = mute
    if channel_volumes is not _UNSET:
        if not isinstance(channel_volumes, Sequence) or isinstance(
            channel_volumes, (str, bytes, bytearray)
        ):
            raise TypeError("channel_volumes must be a sequence")
        values = tuple(
            _non_negative_finite(item, "channel_volumes item")
            for item in channel_volumes
        )
        if not values:
            raise ValueError("channel_volumes must not be empty")
        properties["channelVolumes"] = values
        expected["channel_volumes"] = tuple(_float32(item) for item in values)

    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=node_id,
        selector={"parameter_id": "Props"},
    )
    predicates = tuple(
        ConfirmationPredicateValue(
            target=target,
            operator=ConfirmationOperator.EQUALS,
            path=("values", 0, name),
            expected=value,
        )
        for name, value in expected.items()
    )
    return set_runtime_parameter(
        connection,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        target_kind=RuntimeObjectKind.NODE,
        target_id=node_id,
        parameter_id="Props",
        value=spa_pod.SpaProps(**properties),
        confirmation_predicates=predicates,
        timeout=timeout,
        request_id=request_id,
    )


def set_node_volume(
    connection: object,
    *,
    node_id: int,
    volume: float,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    return set_node_audio_properties(
        connection,
        node_id=node_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        volume=volume,
        timeout=timeout,
        request_id=request_id,
    )


def set_node_mute(
    connection: object,
    *,
    node_id: int,
    mute: bool,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    return set_node_audio_properties(
        connection,
        node_id=node_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        mute=mute,
        timeout=timeout,
        request_id=request_id,
    )


_DEFAULT_NODE_METADATA = {
    "Audio/Sink": ("audio_sink", "default.configured.audio.sink"),
    "Audio/Source": ("audio_source", "default.configured.audio.source"),
    "Video/Source": ("video_source", "default.configured.video.source"),
}


def set_runtime_metadata(
    connection: object,
    *,
    metadata_id: int,
    subject: int,
    key: str,
    value: str,
    expected_generation: int,
    type_name: str | None = "Spa:String",
    confirmation_predicates: Sequence[ConfirmationPredicateValue] | None = None,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Set one metadata entry and await its detached observed value."""

    target = _metadata_target(metadata_id=metadata_id, subject=subject, key=key)
    _required_string(value, "value", allow_empty=True)
    if type_name is not None:
        _required_string(type_name, "type_name")
    predicates = tuple(confirmation_predicates or (
        ConfirmationPredicateValue(
            target=target,
            operator=ConfirmationOperator.EQUALS,
            path=("value",),
            expected=value,
        ),
        ConfirmationPredicateValue(
            target=target,
            operator=ConfirmationOperator.EQUALS,
            path=("type_name",),
            expected=type_name,
        ),
    ))
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.SET_METADATA,
        target=target,
        payload={"type_name": type_name, "value": value},
        confirmation_predicates=predicates,
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request)


def clear_runtime_metadata(
    connection: object,
    *,
    metadata_id: int,
    subject: int,
    key: str,
    expected_generation: int,
    confirmation_predicates: Sequence[ConfirmationPredicateValue] | None = None,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Clear exactly one metadata entry and confirm that entry is absent."""

    target = _metadata_target(metadata_id=metadata_id, subject=subject, key=key)
    predicates = tuple(confirmation_predicates or (
        ConfirmationPredicateValue(
            target=target,
            operator=ConfirmationOperator.ABSENT,
        ),
    ))
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.CLEAR_METADATA,
        target=target,
        payload={},
        confirmation_predicates=predicates,
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request)


def set_default_node(
    connection: object,
    *,
    node_id: int,
    expected_generation: int,
    media_class: str | None = None,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Set WirePlumber's configured default preference for a current node."""

    _pipewire_identifier(node_id, "node_id")
    preflight = _capture_snapshot(connection)
    node = preflight.nodes_by_id.get(node_id)
    if node is None:
        raise ValueError(f"node_id {node_id} is not present in the current runtime")
    selected_media_class = media_class or node.media_class
    if selected_media_class not in _DEFAULT_NODE_METADATA:
        raise ValueError(
            "default node media_class must be Audio/Sink, Audio/Source, or Video/Source"
        )
    if node.media_class != selected_media_class:
        raise ValueError(
            f"node {node_id} has media class {node.media_class!r}, not "
            f"{selected_media_class!r}"
        )
    node_name = node.name or node.properties.get("node.name")
    if not isinstance(node_name, str) or not node_name:
        raise ValueError(f"node {node_id} does not expose a non-empty node.name")
    metadata = _default_metadata(preflight)
    defaults_field, key = _DEFAULT_NODE_METADATA[selected_media_class]
    target = _metadata_target(metadata_id=metadata.id, subject=0, key=key)
    observed_default = MutationTargetValue(
        object_kind=RuntimeObjectKind.METADATA,
        object_id=metadata.id,
        selector={"defaults_field": defaults_field},
    )
    encoded_name = json.dumps({"name": node_name}, separators=(",", ":"))
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.SET_METADATA,
        target=target,
        payload={
            "type_name": "Spa:String:JSON",
            "value": encoded_name,
        },
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.EQUALS,
                path=("value",),
                expected=encoded_name,
            ),
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.EQUALS,
                path=("type_name",),
                expected="Spa:String:JSON",
            ),
            ConfirmationPredicateValue(
                target=observed_default,
                operator=ConfirmationOperator.EQUALS,
                path=("resolved_node_id",),
                expected=node_id,
            ),
        ),
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def clear_default_node(
    connection: object,
    *,
    media_class: str,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Clear one configured default preference without touching other defaults."""

    if media_class not in _DEFAULT_NODE_METADATA:
        raise ValueError(
            "media_class must be Audio/Sink, Audio/Source, or Video/Source"
        )
    preflight = _capture_snapshot(connection)
    metadata = _default_metadata(preflight)
    _, key = _DEFAULT_NODE_METADATA[media_class]
    target = _metadata_target(metadata_id=metadata.id, subject=0, key=key)
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.CLEAR_METADATA,
        target=target,
        payload={},
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.ABSENT,
            ),
        ),
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def set_stream_target(
    connection: object,
    *,
    stream_node_id: int,
    target_node_id: int,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Set a current stream's explicit ``target.object`` metadata override."""

    _pipewire_identifier(stream_node_id, "stream_node_id")
    _pipewire_identifier(target_node_id, "target_node_id")
    preflight = _capture_snapshot(connection)
    stream = preflight.nodes_by_id.get(stream_node_id)
    if stream is None:
        raise ValueError(
            f"stream_node_id {stream_node_id} is not present in the current runtime"
        )
    if not stream.media_class or not stream.media_class.startswith("Stream/"):
        raise ValueError(f"node {stream_node_id} is not a stream node")
    target_node = preflight.nodes_by_id.get(target_node_id)
    if target_node is None:
        raise ValueError(
            f"target_node_id {target_node_id} is not present in the current runtime"
        )
    target_value, type_name = _stream_target_identity(target_node)
    metadata = _default_metadata(preflight)
    target = _metadata_target(
        metadata_id=metadata.id,
        subject=stream_node_id,
        key="target.object",
    )
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.SET_METADATA,
        target=target,
        payload={"type_name": type_name, "value": target_value},
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.EQUALS,
                path=("value",),
                expected=target_value,
            ),
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.EQUALS,
                path=("type_name",),
                expected=type_name,
            ),
        ),
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def clear_stream_target(
    connection: object,
    *,
    stream_node_id: int,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Clear only a current stream's explicit ``target.object`` override."""

    _pipewire_identifier(stream_node_id, "stream_node_id")
    preflight = _capture_snapshot(connection)
    stream = preflight.nodes_by_id.get(stream_node_id)
    if stream is None:
        raise ValueError(
            f"stream_node_id {stream_node_id} is not present in the current runtime"
        )
    if not stream.media_class or not stream.media_class.startswith("Stream/"):
        raise ValueError(f"node {stream_node_id} is not a stream node")
    metadata = _default_metadata(preflight)
    target = _metadata_target(
        metadata_id=metadata.id,
        subject=stream_node_id,
        key="target.object",
    )
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.CLEAR_METADATA,
        target=target,
        payload={},
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.ABSENT,
            ),
        ),
        timeout=timeout,
    )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def _metadata_target(*, metadata_id: int, subject: int, key: str) -> MutationTargetValue:
    _pipewire_identifier(metadata_id, "metadata_id")
    _pipewire_identifier(subject, "subject")
    _required_string(key, "key")
    return MutationTargetValue(
        object_kind=RuntimeObjectKind.METADATA,
        object_id=metadata_id,
        selector={"subject": subject, "key": key},
    )


def _default_metadata(snapshot: object):
    metadata = next((item for item in snapshot.metadata if item.name == "default"), None)
    if metadata is None and snapshot.defaults.metadata_id is not None:
        metadata = snapshot.metadata_by_id.get(snapshot.defaults.metadata_id)
    if metadata is None:
        raise ValueError("the current runtime does not expose default metadata")
    return metadata


def _stream_target_identity(node: object) -> tuple[str, str]:
    serial = node.properties.get("object.serial")
    if isinstance(serial, int) and not isinstance(serial, bool) and serial >= 0:
        return str(serial), "Spa:Id"
    if isinstance(serial, str) and serial.isdecimal():
        return serial, "Spa:Id"
    name = node.name or node.properties.get("node.name")
    if isinstance(name, str) and name:
        return name, "Spa:String"
    raise ValueError(f"node {node.id} exposes neither object.serial nor node.name")


def _pipewire_identifier(value: object, name: str) -> int:
    result = _identifier(value, name)
    if result > 0xFFFFFFFF:
        raise ValueError(f"{name} exceeds the PipeWire ID range")
    return result


def select_device_profile(
    connection: object,
    *,
    profile: ProfileValue,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Select one currently enumerated device profile and confirm it active."""

    from wyreplumber import spa_pod

    if not isinstance(profile, ProfileValue):
        raise TypeError("profile must be a detached ProfileValue")
    _pipewire_identifier(profile.device_id, "profile.device_id")
    _pipewire_identifier(profile.index, "profile.index")
    confirmation_target = MutationTargetValue(
        object_kind=RuntimeObjectKind.DEVICE,
        object_id=profile.device_id,
        selector={"profile_index": profile.index},
    )
    request = _parameter_selection_request(
        operation=MutationOperation.SELECT_PROFILE,
        parameter_id="Profile",
        device_id=profile.device_id,
        value=spa_pod.SpaParamProfile(index=profile.index),
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=confirmation_target,
                operator=ConfirmationOperator.EQUALS,
                path=("active",),
                expected=True,
            ),
            ConfirmationPredicateValue(
                target=confirmation_target,
                operator=ConfirmationOperator.EQUALS,
                path=("name",),
                expected=profile.name,
            ),
        ),
        timeout=timeout,
        request_id=request_id,
    )
    preflight = _capture_snapshot(connection)
    if _preflight_is_stale(request, preflight):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    if profile.device_id not in preflight.devices_by_id:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_NOT_FOUND,
            f"device {profile.device_id} is not present in the current runtime",
        )
    current = preflight.profiles_by_key.get((profile.device_id, profile.index))
    if current is None:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_NOT_FOUND,
            f"profile {profile.index} is not enumerated for device {profile.device_id}",
        )
    if current.name != profile.name:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_IDENTITY_CHANGED,
            "the profile index now identifies a different profile",
            details={"expected_name": profile.name, "observed_name": current.name},
        )
    if len(_confirmations_from_snapshot(
        preflight, request.confirmation_predicates
    )) == len(request.confirmation_predicates):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    if current.available is Availability.NO:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_UNAVAILABLE,
            f"profile {profile.name!r} is currently unavailable",
        )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def select_device_route(
    connection: object,
    *,
    route: RouteValue,
    expected_generation: int,
    expected_sequence: int | None = None,
    volume: object = _UNSET,
    mute: object = _UNSET,
    channel_volumes: object = _UNSET,
    save: bool = True,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Select one current device route and optionally write its audio props."""

    from wyreplumber import spa_pod

    if not isinstance(route, RouteValue):
        raise TypeError("route must be a detached RouteValue")
    _pipewire_identifier(route.device_id, "route.device_id")
    _pipewire_identifier(route.index, "route.index")
    if not isinstance(save, bool):
        raise TypeError("save must be a boolean")

    properties: dict[str, object] = {}
    expected: dict[str, object] = {}
    if volume is not _UNSET:
        properties["volume"] = _non_negative_finite(volume, "volume")
        expected["volume"] = _float32(properties["volume"])
    if mute is not _UNSET:
        if not isinstance(mute, bool):
            raise TypeError("mute must be a boolean")
        properties["mute"] = mute
        expected["mute"] = mute
    if channel_volumes is not _UNSET:
        if not isinstance(channel_volumes, Sequence) or isinstance(
            channel_volumes, (str, bytes, bytearray)
        ):
            raise TypeError("channel_volumes must be a sequence")
        values = tuple(
            _non_negative_finite(item, "channel_volumes item")
            for item in channel_volumes
        )
        if not values:
            raise ValueError("channel_volumes must not be empty")
        properties["channelVolumes"] = values
        expected["channel_volumes"] = tuple(_float32(item) for item in values)

    spa_device = _route_spa_device(route)
    route_properties = spa_pod.SpaProps(**properties) if properties else None
    pod_fields: dict[str, object] = {
        "index": route.index,
        "device": spa_device,
        "save": save,
    }
    if route_properties is not None:
        pod_fields["props"] = route_properties
    confirmation_target = MutationTargetValue(
        object_kind=RuntimeObjectKind.DEVICE,
        object_id=route.device_id,
        selector={"route_index": route.index},
    )
    predicates = [
        ConfirmationPredicateValue(
            target=confirmation_target,
            operator=ConfirmationOperator.EQUALS,
            path=("active",),
            expected=True,
        ),
        ConfirmationPredicateValue(
            target=confirmation_target,
            operator=ConfirmationOperator.EQUALS,
            path=("name",),
            expected=route.name,
        ),
    ]
    predicates.extend(
        ConfirmationPredicateValue(
            target=confirmation_target,
            operator=ConfirmationOperator.EQUALS,
            path=(name,),
            expected=value,
        )
        for name, value in expected.items()
    )
    request = _parameter_selection_request(
        operation=MutationOperation.SELECT_ROUTE,
        parameter_id="Route",
        device_id=route.device_id,
        value=spa_pod.SpaParamRoute(**pod_fields),
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        confirmation_predicates=predicates,
        timeout=timeout,
        request_id=request_id,
    )
    preflight = _capture_snapshot(connection)
    if _preflight_is_stale(request, preflight):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    if route.device_id not in preflight.devices_by_id:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_NOT_FOUND,
            f"device {route.device_id} is not present in the current runtime",
        )
    current = preflight.routes_by_key.get((route.device_id, route.index))
    if current is None:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_NOT_FOUND,
            f"route {route.index} is not enumerated for device {route.device_id}",
        )
    if (
        current.name != route.name
        or current.direction != route.direction
        or _route_spa_device(current) != spa_device
    ):
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_IDENTITY_CHANGED,
            "the route index now identifies a different route",
            details={"expected_name": route.name, "observed_name": current.name},
        )
    if len(_confirmations_from_snapshot(
        preflight, request.confirmation_predicates
    )) == len(request.confirmation_predicates):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    if current.available is Availability.NO:
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_UNAVAILABLE,
            f"route {route.name!r} is currently unavailable",
        )
    active_profile_ids = {
        profile.index
        for profile in preflight.profiles
        if profile.device_id == route.device_id and profile.active
    }
    if (
        current.profile_ids
        and active_profile_ids
        and active_profile_ids.isdisjoint(current.profile_ids)
    ):
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_UNAVAILABLE,
            f"route {route.name!r} is not valid for the active device profile",
            details={"active_profile_ids": sorted(active_profile_ids)},
        )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def _parameter_selection_request(
    *,
    operation: MutationOperation,
    parameter_id: str,
    device_id: int,
    value: object,
    expected_generation: int,
    expected_sequence: int | None,
    confirmation_predicates: Sequence[ConfirmationPredicateValue],
    timeout: float,
    request_id: str | None,
) -> MutationRequest:
    raw_pod = _parameter_pod_bytes(value, pod_type=None)
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.DEVICE,
        object_id=device_id,
        selector={"parameter_id": parameter_id},
    )
    return MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=operation,
        target=target,
        payload={
            "flags": 0,
            "pod_base64": base64.b64encode(raw_pod).decode("ascii"),
        },
        confirmation_predicates=confirmation_predicates,
        timeout=timeout,
    )


def _route_spa_device(route: RouteValue) -> int:
    value = route.properties.get("spa_device_index")
    if value is None:
        raise ValueError(
            f"route {route.index} does not expose its SPA device identity"
        )
    return _pipewire_identifier(value, "route SPA device identity")


def _preflight_is_stale(request: MutationRequest, snapshot: object) -> bool:
    return snapshot.generation != request.expected_generation or (
        request.expected_sequence is not None
        and snapshot.sequence != request.expected_sequence + 1
    )


def _selection_failure(
    request: MutationRequest,
    code: MutationFailureCode,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> MutationOutcome:
    return _failure_outcome(
        request,
        status=MutationStatus.REJECTED,
        phase=MutationFailurePhase.PRECONDITION,
        code=code,
        message=message,
        details=details,
    )


_RESERVED_LINK_PROPERTIES = {
    "link.output.node",
    "link.output.port",
    "link.input.node",
    "link.input.port",
    "object.linger",
    "open-cinema.owner",
    "open-cinema.desired-id",
}


def create_managed_link(
    connection: object,
    *,
    owner: str,
    desired_id: str,
    output_node_id: int,
    output_port_id: int,
    input_node_id: int,
    input_port_id: int,
    expected_generation: int,
    expected_sequence: int | None = None,
    passive: bool = False,
    properties: Mapping[str, str] | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Create one explicitly owned link without adopting existing topology."""

    _required_string(owner, "owner")
    _required_string(desired_id, "desired_id")
    endpoints = {
        "output_node_id": _pipewire_identifier(output_node_id, "output_node_id"),
        "output_port_id": _pipewire_identifier(output_port_id, "output_port_id"),
        "input_node_id": _pipewire_identifier(input_node_id, "input_node_id"),
        "input_port_id": _pipewire_identifier(input_port_id, "input_port_id"),
    }
    if not isinstance(passive, bool):
        raise TypeError("passive must be a boolean")
    link_properties = _validated_link_properties(properties)
    if "link.passive" in link_properties:
        raise ValueError("link.passive must be supplied through the passive argument")
    if passive:
        link_properties["link.passive"] = "true"

    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.LINK,
        object_id=desired_id,
        selector={"owner": owner, "desired_id": desired_id, **endpoints},
    )
    predicates = tuple(
        ConfirmationPredicateValue(
            target=target,
            operator=ConfirmationOperator.EQUALS,
            path=(name,),
            expected=value,
        )
        for name, value in endpoints.items()
    )
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.CREATE_LINK,
        target=target,
        payload={"properties": link_properties},
        confirmation_predicates=predicates,
        timeout=timeout,
    )
    preflight = _capture_snapshot(connection)
    if _preflight_is_stale(request, preflight):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    endpoint_failure = _validate_link_endpoints(request, preflight, endpoints)
    if endpoint_failure is not None:
        return endpoint_failure

    same_identity = [
        link
        for link in preflight.links
        if link.owner == owner and link.desired_id == desired_id
    ]
    if len(same_identity) > 1:
        return _link_ownership_conflict(
            request,
            "multiple links already claim the same managed identity",
            links=same_identity,
        )
    if same_identity:
        existing = same_identity[0]
        if _link_has_endpoints(existing, endpoints):
            return _execute_confirmed_mutation(
                connection, request, preflight=preflight
            )
        return _link_ownership_conflict(
            request,
            "the managed identity already belongs to different endpoints",
            links=same_identity,
        )

    same_topology = [
        link for link in preflight.links if _link_has_endpoints(link, endpoints)
    ]
    if same_topology:
        return _link_ownership_conflict(
            request,
            "the requested topology already exists without this managed identity",
            links=same_topology,
        )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def remove_managed_link(
    connection: object,
    *,
    owner: str,
    desired_id: str,
    expected_generation: int,
    expected_sequence: int | None = None,
    timeout: float = 5.0,
    request_id: str | None = None,
) -> MutationOutcome:
    """Remove only the link carrying the requested managed identity."""

    _required_string(owner, "owner")
    _required_string(desired_id, "desired_id")
    preflight = _capture_snapshot(connection)
    matches = [
        link
        for link in preflight.links
        if link.owner == owner and link.desired_id == desired_id
    ]
    link_id = matches[0].id if len(matches) == 1 else 0
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.LINK,
        object_id=desired_id,
        selector={"owner": owner, "desired_id": desired_id},
    )
    request = MutationRequest.create(
        request_id=request_id,
        expected_generation=expected_generation,
        expected_sequence=expected_sequence,
        operation=MutationOperation.REMOVE_LINK,
        target=target,
        payload={"link_id": link_id},
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.ABSENT,
            ),
        ),
        timeout=timeout,
    )
    if _preflight_is_stale(request, preflight):
        return _execute_confirmed_mutation(connection, request, preflight=preflight)
    if len(matches) > 1:
        return _link_ownership_conflict(
            request,
            "multiple links claim the managed identity; none were removed",
            links=matches,
        )
    return _execute_confirmed_mutation(connection, request, preflight=preflight)


def _validated_link_properties(
    properties: Mapping[str, str] | None,
) -> dict[str, str]:
    if properties is None:
        return {}
    if not isinstance(properties, Mapping):
        raise TypeError("properties must be a mapping")
    result: dict[str, str] = {}
    for key, value in properties.items():
        _required_string(key, "link property name")
        if key in _RESERVED_LINK_PROPERTIES:
            raise ValueError(f"link property {key!r} is managed by the dispatcher")
        if not isinstance(value, str):
            raise TypeError("link property values must be strings")
        result[key] = value
    return result


def _validate_link_endpoints(
    request: MutationRequest,
    snapshot: object,
    endpoints: Mapping[str, int],
) -> MutationOutcome | None:
    output_node = snapshot.nodes_by_id.get(endpoints["output_node_id"])
    input_node = snapshot.nodes_by_id.get(endpoints["input_node_id"])
    output_port = snapshot.ports_by_id.get(endpoints["output_port_id"])
    input_port = snapshot.ports_by_id.get(endpoints["input_port_id"])
    if any(
        endpoint is None
        for endpoint in (output_node, input_node, output_port, input_port)
    ):
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_NOT_FOUND,
            "one or more requested link endpoints are absent",
        )
    if (
        output_port.node_id != output_node.id
        or input_port.node_id != input_node.id
        or output_port.direction.value != "output"
        or input_port.direction.value != "input"
    ):
        return _selection_failure(
            request,
            MutationFailureCode.TARGET_IDENTITY_CHANGED,
            "a port no longer belongs to the requested node and direction",
        )
    return None


def _link_has_endpoints(link: LinkValue, endpoints: Mapping[str, int]) -> bool:
    return all(getattr(link, name) == value for name, value in endpoints.items())


def _link_ownership_conflict(
    request: MutationRequest,
    message: str,
    *,
    links: Sequence[LinkValue],
) -> MutationOutcome:
    return _selection_failure(
        request,
        MutationFailureCode.OWNERSHIP_CONFLICT,
        message,
        details={
            "conflicting_links": [
                {
                    "id": link.id,
                    "owner": link.owner,
                    "desired_id": link.desired_id,
                }
                for link in links
            ]
        },
    )


def _capture_snapshot(connection: object):
    from .snapshot import capture_runtime_snapshot

    return capture_runtime_snapshot(connection)


def _confirmations_from_snapshot(
    snapshot: object,
    predicates: Sequence[ConfirmationPredicateValue],
) -> tuple[MutationConfirmationValue, ...]:
    confirmations: list[MutationConfirmationValue] = []
    for predicate in predicates:
        observation = _snapshot_observation(snapshot, predicate.target)
        if predicate.matches(observation):
            confirmations.append(
                MutationConfirmationValue(
                    generation=snapshot.generation,
                    sequence=snapshot.sequence,
                    observed_at=snapshot.captured_at,
                    predicate=predicate,
                    observation=observation,
                )
            )
    return tuple(confirmations)


def _snapshot_observation(snapshot: object, target: MutationTargetValue) -> object:
    link_owner = target.selector.get("owner")
    link_desired_id = target.selector.get("desired_id")
    if (
        target.object_kind is RuntimeObjectKind.LINK
        and isinstance(link_owner, str)
        and isinstance(link_desired_id, str)
    ):
        matches = [
            link
            for link in snapshot.links
            if link.owner == link_owner and link.desired_id == link_desired_id
        ]
        return matches[0] if len(matches) == 1 else None
    profile_index = target.selector.get("profile_index")
    if isinstance(profile_index, int) and isinstance(target.object_id, int):
        return snapshot.profiles_by_key.get((target.object_id, profile_index))
    route_index = target.selector.get("route_index")
    if isinstance(route_index, int) and isinstance(target.object_id, int):
        return snapshot.routes_by_key.get((target.object_id, route_index))
    parameter_id = target.selector.get("parameter_id")
    if isinstance(parameter_id, str) and isinstance(target.object_id, int):
        return snapshot.parameters_by_key.get(
            (target.object_kind.value, target.object_id, parameter_id)
        )
    defaults_field = target.selector.get("defaults_field")
    if isinstance(defaults_field, str):
        return getattr(snapshot.defaults, defaults_field, None)
    metadata_subject = target.selector.get("subject")
    metadata_key = target.selector.get("key")
    if (
        target.object_kind is RuntimeObjectKind.METADATA
        and isinstance(target.object_id, int)
        and isinstance(metadata_subject, int)
        and not isinstance(metadata_subject, bool)
        and isinstance(metadata_key, str)
    ):
        metadata = snapshot.metadata_by_id.get(target.object_id)
        if metadata is None:
            return None
        return next(
            (
                entry
                for entry in reversed(metadata.entries)
                if entry.subject == metadata_subject and entry.key == metadata_key
            ),
            None,
        )
    if not isinstance(target.object_id, int):
        return None
    indexes = {
        RuntimeObjectKind.DEVICE: snapshot.devices_by_id,
        RuntimeObjectKind.NODE: snapshot.nodes_by_id,
        RuntimeObjectKind.PORT: snapshot.ports_by_id,
        RuntimeObjectKind.LINK: snapshot.links_by_id,
        RuntimeObjectKind.METADATA: snapshot.metadata_by_id,
    }
    index = indexes.get(target.object_kind)
    return None if index is None else index.get(target.object_id)


def _ticket_failure_outcome(
    request: MutationRequest, ticket: MutationDispatchTicketValue
) -> MutationOutcome:
    code = ticket.failure_code or MutationFailureCode.INTERNAL_ERROR
    if ticket.disposition is MutationDispatchDisposition.CANCELLED:
        status = MutationStatus.CANCELLED
        phase = MutationFailurePhase.CANCELLATION
    elif ticket.disposition is MutationDispatchDisposition.FAILED:
        status = MutationStatus.FAILED
        phase = MutationFailurePhase.EXECUTION
    elif code is MutationFailureCode.UNSUPPORTED_OPERATION:
        status = MutationStatus.REJECTED
        phase = MutationFailurePhase.VALIDATION
    else:
        status = MutationStatus.REJECTED
        phase = MutationFailurePhase.PRECONDITION
    return _failure_outcome(
        request,
        status=status,
        phase=phase,
        code=code,
        message=f"native mutation dispatch returned {code.value}",
        retryable=code is MutationFailureCode.GENERATION_LOST,
        details={
            "dispatch_order": ticket.dispatch_order,
            "observed_generation": ticket.observed_generation,
            "observed_sequence": ticket.observed_sequence,
        },
    )


def _runtime_unavailable_outcome(
    request: MutationRequest,
    error: RuntimeError,
    *,
    confirmations: Sequence[MutationConfirmationValue] = (),
) -> MutationOutcome:
    message = str(error)
    stopped = "stopped" in message.lower() or "not ready" in message.lower()
    return _failure_outcome(
        request,
        status=MutationStatus.CANCELLED if stopped else MutationStatus.FAILED,
        phase=(
            MutationFailurePhase.CANCELLATION
            if stopped
            else MutationFailurePhase.EXECUTION
        ),
        code=(
            MutationFailureCode.RUNTIME_STOPPED
            if stopped
            else MutationFailureCode.INTERNAL_ERROR
        ),
        message=message,
        confirmations=confirmations,
    )


def _failure_outcome(
    request: MutationRequest,
    *,
    status: MutationStatus,
    phase: MutationFailurePhase,
    code: MutationFailureCode,
    message: str,
    retryable: bool = False,
    details: Mapping[str, object] | None = None,
    confirmations: Sequence[MutationConfirmationValue] = (),
) -> MutationOutcome:
    return MutationOutcome(
        request_id=request.request_id,
        generation=request.expected_generation,
        operation=request.operation,
        status=status,
        completed_at=datetime.now(timezone.utc),
        confirmations=tuple(confirmations),
        failure=MutationFailureValue(
            phase=phase,
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
    )


def _parameter_pod_bytes(value: object, *, pod_type: int | None) -> bytes:
    from wyreplumber.spa_pod import build_spa_pod

    if pod_type is not None:
        _identifier(pod_type, "pod_type")
    if isinstance(value, Mapping) and "data" in value:
        data = value["data"]
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("raw SPA pod data must be bytes-like")
        raw = bytes(data)
    elif isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
    else:
        raw = build_spa_pod(value, pod_type)
    if len(raw) < 8:
        raise ValueError("raw SPA pod is smaller than its header")
    size, _ = struct.unpack_from("<II", raw)
    if len(raw) < 8 + size:
        raise ValueError("raw SPA pod data is shorter than its declared size")
    return raw


def _non_negative_finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _named_timestamp(value: object, name: str) -> str:
    try:
        return _timestamp(value)
    except (TypeError, ValueError) as error:
        raise type(error)(str(error).replace("captured_at", name)) from error


def _parse_timestamp(value: datetime | str) -> datetime:
    normalized = _named_timestamp(value, "timestamp")
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _resolve_path(value: object, path: Sequence[str | int]) -> tuple[bool, object]:
    current = value
    for component in path:
        if isinstance(component, str):
            if not isinstance(current, Mapping) or component not in current:
                return False, None
            current = current[component]
        else:
            if not isinstance(current, Sequence) or isinstance(
                current, (str, bytes, bytearray)
            ) or component >= len(current):
                return False, None
            current = current[component]
    return True, current


def _comparable(value: object) -> object:
    if isinstance(value, RuntimeValue):
        return freeze_json(value.to_dict())
    return freeze_json(value)
