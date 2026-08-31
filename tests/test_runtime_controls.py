import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from wyreplumber.runtime import (
    ConfirmationOperator,
    ConfirmationPredicateValue,
    MutationConfirmationValue,
    MutationFailureCode,
    MutationFailurePhase,
    MutationFailureValue,
    MutationOperation,
    MutationOutcome,
    MutationRequest,
    MutationStatus,
    MutationTargetValue,
    RuntimeObjectKind,
    runtime_value_from_dict,
)


def _target():
    return MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=20,
        selector={"parameter_id": "Props"},
    )


def _predicate(*, operator=ConfirmationOperator.EQUALS, expected=False):
    return ConfirmationPredicateValue(
        target=_target(),
        operator=operator,
        path=("values", 0, "mute"),
        expected=expected,
    )


def _request(**changes):
    values = {
        "request_id": "request-1",
        "expected_generation": 7,
        "expected_sequence": 42,
        "operation": MutationOperation.SET_PARAMETER,
        "target": _target(),
        "requested_at": "2026-08-22T12:00:00+00:00",
        "deadline_at": "2026-08-22T12:00:05Z",
        "payload": {"mute": False, "nested": {"channels": ["FL", "FR"]}},
        "confirmation_predicates": (_predicate(),),
    }
    values.update(changes)
    return MutationRequest(**values)


def test_mutation_request_is_detached_immutable_and_json_round_trippable():
    request = _request()
    encoded = json.loads(json.dumps(request.to_dict(), allow_nan=False))
    restored = runtime_value_from_dict(encoded)

    assert restored == request
    assert MutationRequest.from_dict(encoded) == request
    assert request.target.selector["parameter_id"] == "Props"
    assert request.payload["nested"]["channels"] == ("FL", "FR")
    with pytest.raises(FrozenInstanceError):
        request.expected_generation = 8
    with pytest.raises(TypeError):
        request.payload["mute"] = True


def test_request_factory_assigns_unique_identity_and_absolute_deadline():
    first = MutationRequest.create(
        expected_generation=7,
        expected_sequence=42,
        operation=MutationOperation.SET_PARAMETER,
        target=_target(),
        payload={"mute": False},
        confirmation_predicates=(_predicate(),),
        timeout=2.5,
        now=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
    )
    second = MutationRequest.create(
        expected_generation=7,
        operation=MutationOperation.SET_PARAMETER,
        target=_target(),
        confirmation_predicates=(_predicate(),),
        timeout=0,
        now="2026-08-22T12:00:00Z",
    )

    assert first.request_id != second.request_id
    assert first.requested_at == "2026-08-22T12:00:00Z"
    assert first.deadline_at == "2026-08-22T12:00:02.500000Z"
    assert not first.is_expired("2026-08-22T12:00:02.499999Z")
    assert first.is_expired(first.deadline_at)
    assert second.is_expired(second.requested_at)
    assert "tolerance" not in first.confirmation_predicates[0].to_dict()


@pytest.mark.parametrize(
    ("changes", "error"),
    (
        ({"request_id": ""}, "request_id"),
        ({"expected_generation": -1}, "expected_generation"),
        ({"expected_sequence": -1}, "expected_sequence"),
        ({"operation": "future_operation"}, "operation"),
        ({"target": object()}, "target"),
        ({"requested_at": "2026-08-22T12:00:00"}, "timezone"),
        ({"deadline_at": "2026-08-22T11:59:59Z"}, "must not precede"),
        ({"payload": {"native": object()}}, "JSON-compatible"),
        ({"confirmation_predicates": ()}, "at least one"),
        ({"confirmation_predicates": (object(),)}, "ConfirmationPredicateValue"),
    ),
)
def test_mutation_request_rejects_invalid_contract_values(changes, error):
    with pytest.raises((TypeError, ValueError), match=error):
        _request(**changes)


@pytest.mark.parametrize("timeout", (True, "5", float("inf"), -0.1))
def test_request_factory_rejects_invalid_deadlines(timeout):
    expected_error = TypeError if timeout in (True, "5") else ValueError
    with pytest.raises(expected_error):
        MutationRequest.create(
            expected_generation=7,
            operation=MutationOperation.SET_PARAMETER,
            target=_target(),
            confirmation_predicates=(_predicate(),),
            timeout=timeout,
        )


def test_confirmation_predicates_use_declarative_paths_without_callbacks():
    equals = _predicate()
    present = ConfirmationPredicateValue(
        target=_target(),
        operator=ConfirmationOperator.PRESENT,
        path=("values", 0),
    )
    absent = ConfirmationPredicateValue(
        target=_target(),
        operator=ConfirmationOperator.ABSENT,
        path=("values", 1),
    )
    observation = {"values": [{"mute": False}]}

    assert equals.matches(observation)
    assert present.matches(observation)
    assert absent.matches(observation)
    assert not equals.matches({"values": [{"mute": True}]})
    assert not equals.matches(None)

    approximate = ConfirmationPredicateValue(
        target=_target(),
        operator=ConfirmationOperator.APPROXIMATELY_EQUALS,
        path=("mixer", "volume"),
        expected=0.42,
        tolerance=0.005,
    )
    assert approximate.matches({"mixer": {"volume": 0.423}})
    assert not approximate.matches({"mixer": {"volume": 0.426}})

    with pytest.raises(ValueError, match="must not set expected"):
        ConfirmationPredicateValue(
            target=_target(),
            operator=ConfirmationOperator.PRESENT,
            expected=True,
        )
    with pytest.raises(TypeError, match="JSON-compatible"):
        ConfirmationPredicateValue(
            target=_target(),
            operator=ConfirmationOperator.EQUALS,
            expected=lambda: True,
        )


def test_confirmed_outcome_contains_the_exact_confirming_observation():
    predicate = _predicate()
    confirmation = MutationConfirmationValue(
        generation=7,
        sequence=44,
        observed_at="2026-08-22T12:00:01Z",
        predicate=predicate,
        observation={"values": [{"mute": False}]},
    )
    outcome = MutationOutcome(
        request_id="request-1",
        generation=7,
        operation=MutationOperation.SET_PARAMETER,
        status=MutationStatus.CONFIRMED,
        completed_at="2026-08-22T12:00:01Z",
        confirmations=(confirmation,),
    )
    restored = MutationOutcome.from_dict(
        json.loads(json.dumps(outcome.to_dict(), allow_nan=False))
    )

    assert outcome.succeeded
    assert restored == outcome
    assert restored.confirmations[0].sequence == 44


@pytest.mark.parametrize(
    ("status", "phase", "code"),
    (
        (
            MutationStatus.REJECTED,
            MutationFailurePhase.PRECONDITION,
            MutationFailureCode.STALE_GENERATION,
        ),
        (
            MutationStatus.FAILED,
            MutationFailurePhase.EXECUTION,
            MutationFailureCode.NATIVE_REJECTED,
        ),
        (
            MutationStatus.TIMED_OUT,
            MutationFailurePhase.CONFIRMATION,
            MutationFailureCode.CONFIRMATION_TIMEOUT,
        ),
        (
            MutationStatus.CANCELLED,
            MutationFailurePhase.CANCELLATION,
            MutationFailureCode.GENERATION_LOST,
        ),
        (
            MutationStatus.CANCELLED,
            MutationFailurePhase.CANCELLATION,
            MutationFailureCode.RUNTIME_STOPPED,
        ),
    ),
)
def test_unsuccessful_outcomes_are_structured_and_round_trippable(
    status, phase, code
):
    outcome = MutationOutcome(
        request_id="request-1",
        generation=7,
        operation=MutationOperation.SET_PARAMETER,
        status=status,
        completed_at="2026-08-22T12:00:05Z",
        failure=MutationFailureValue(
            phase=phase,
            code=code,
            message="controlled failure",
            retryable=code is MutationFailureCode.GENERATION_LOST,
            details={"expected_generation": 7, "actual_generation": 8},
        ),
    )

    assert not outcome.succeeded
    assert MutationOutcome.from_dict(outcome.to_dict()) == outcome
    assert outcome.failure.code is code


def test_outcome_invariants_prevent_invented_success_or_ambiguous_failure():
    with pytest.raises(ValueError, match="confirming observations"):
        MutationOutcome(
            request_id="request-1",
            generation=7,
            operation=MutationOperation.SET_PARAMETER,
            status=MutationStatus.CONFIRMED,
            completed_at="2026-08-22T12:00:01Z",
        )
    with pytest.raises(ValueError, match="structured failure"):
        MutationOutcome(
            request_id="request-1",
            generation=7,
            operation=MutationOperation.SET_PARAMETER,
            status=MutationStatus.REJECTED,
            completed_at="2026-08-22T12:00:01Z",
        )
    with pytest.raises(ValueError, match="incompatible failure code"):
        MutationOutcome(
            request_id="request-1",
            generation=7,
            operation=MutationOperation.SET_PARAMETER,
            status=MutationStatus.TIMED_OUT,
            completed_at="2026-08-22T12:00:01Z",
            failure=MutationFailureValue(
                phase=MutationFailurePhase.EXECUTION,
                code=MutationFailureCode.NATIVE_REJECTED,
                message="not a timeout",
            ),
        )
    with pytest.raises(ValueError, match="does not satisfy"):
        MutationConfirmationValue(
            generation=7,
            sequence=44,
            observed_at="2026-08-22T12:00:01Z",
            predicate=_predicate(),
            observation={"values": [{"mute": True}]},
        )
