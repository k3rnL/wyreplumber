import base64
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from wyreplumber import spa_pod
from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    ConfirmationOperator,
    ConfirmationPredicateValue,
    MutationDispatchDisposition,
    MutationDispatchTicketValue,
    MutationFailureCode,
    MutationOperation,
    MutationRequest,
    MutationTargetValue,
    RuntimeObjectKind,
    capture_runtime_snapshot,
    dispatch_runtime_mutation,
    mutation_dispatch_ticket_from_payload,
)


def _request(
    *,
    request_id="request-1",
    generation=1,
    sequence=None,
    operation=MutationOperation.SET_PARAMETER,
):
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=999_999,
        selector={"parameter_id": "Props"},
    )
    predicate = ConfirmationPredicateValue(
        target=target,
        operator=ConfirmationOperator.EQUALS,
        path=("values", 0, "mute"),
        expected=False,
    )
    return MutationRequest(
        request_id=request_id,
        expected_generation=generation,
        expected_sequence=sequence,
        operation=operation,
        target=target,
        requested_at="2026-08-22T12:00:00Z",
        deadline_at="2099-08-22T12:00:00Z",
        payload={
            "flags": 0,
            "pod_base64": base64.b64encode(
                spa_pod.build_spa_pod(spa_pod.SpaProps(mute=False))
            ).decode("ascii"),
        },
        confirmation_predicates=(predicate,),
    )


def _ready_payload():
    return {
        "payload_version": 1,
        "request_id": "request-1",
        "operation": "set_parameter",
        "dispatch_order": 3,
        "disposition": "ready",
        "expected_generation": 7,
        "expected_sequence": 42,
        "observed_generation": 7,
        "observed_sequence": 42,
        "failure_code": None,
    }


def test_native_dispatch_ticket_is_detached_and_round_trippable():
    ticket = mutation_dispatch_ticket_from_payload(_ready_payload())
    restored = MutationDispatchTicketValue.from_dict(
        json.loads(json.dumps(ticket.to_dict(), allow_nan=False))
    )

    assert restored == ticket
    assert ticket.disposition is MutationDispatchDisposition.READY
    assert ticket.failure_code is None


@pytest.mark.parametrize(
    ("change", "error"),
    (
        ({"payload_version": 2}, "unsupported"),
        ({"future": True}, "unknown fields"),
    ),
)
def test_native_dispatch_payload_rejects_contract_drift(change, error):
    payload = _ready_payload()
    payload.update(change)

    with pytest.raises(ValueError, match=error):
        mutation_dispatch_ticket_from_payload(payload)


def test_native_dispatch_enters_wp_fifo_and_validates_sequence(pipewire_socket):
    connection = WPConnection()
    first = capture_runtime_snapshot(connection)
    ready = dispatch_runtime_mutation(
        connection,
        _request(generation=first.generation, sequence=first.sequence),
    )
    second = capture_runtime_snapshot(connection)
    stale = dispatch_runtime_mutation(
        connection,
        _request(
            request_id="stale-sequence",
            generation=second.generation,
            sequence=first.sequence,
        ),
    )

    assert ready.disposition is MutationDispatchDisposition.REJECTED
    assert ready.dispatch_order == 1
    assert ready.failure_code is MutationFailureCode.TARGET_NOT_FOUND
    assert ready.observed_generation == first.generation
    assert ready.observed_sequence == first.sequence
    assert stale.disposition is MutationDispatchDisposition.REJECTED
    assert stale.dispatch_order == 2
    assert stale.failure_code is MutationFailureCode.STALE_SEQUENCE
    assert stale.observed_sequence == second.sequence


def test_native_dispatch_rejects_stale_generation_before_enqueue(pipewire_socket):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    ticket = dispatch_runtime_mutation(
        connection,
        _request(generation=snapshot.generation + 1),
    )

    assert ticket.disposition is MutationDispatchDisposition.REJECTED
    assert ticket.dispatch_order == 0
    assert ticket.failure_code is MutationFailureCode.STALE_GENERATION
    assert ticket.observed_generation == snapshot.generation


def test_concurrent_callers_receive_one_defined_fifo_order(pipewire_socket):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    requests = tuple(
        _request(request_id=f"request-{index}", generation=snapshot.generation)
        for index in range(32)
    )

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        tickets = tuple(pool.map(
            lambda request: dispatch_runtime_mutation(connection, request),
            requests,
        ))

    assert all(
        ticket.disposition is MutationDispatchDisposition.REJECTED
        and ticket.failure_code is MutationFailureCode.TARGET_NOT_FOUND
        for ticket in tickets
    )
    assert sorted(ticket.dispatch_order for ticket in tickets) == list(range(1, 33))
    assert len({ticket.request_id for ticket in tickets}) == len(requests)


def test_snapshot_reads_remain_coherent_during_concurrent_mutations(pipewire_socket):
    connection = WPConnection()
    baseline = capture_runtime_snapshot(connection)

    def dispatch(index):
        return dispatch_runtime_mutation(
            connection,
            _request(
                request_id=f"mixed-request-{index}",
                generation=baseline.generation,
            ),
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        mutation_futures = [pool.submit(dispatch, index) for index in range(16)]
        snapshot_futures = [
            pool.submit(capture_runtime_snapshot, connection)
            for _ in range(16)
        ]
        tickets = tuple(future.result() for future in mutation_futures)
        snapshots = tuple(future.result() for future in snapshot_futures)

    assert sorted(ticket.dispatch_order for ticket in tickets) == list(range(1, 17))
    assert all(
        ticket.failure_code is MutationFailureCode.TARGET_NOT_FOUND
        for ticket in tickets
    )
    assert all(snapshot.generation == baseline.generation for snapshot in snapshots)
    assert len({snapshot.sequence for snapshot in snapshots}) == len(snapshots)
    assert all(snapshot.is_coherent for snapshot in snapshots)


def test_reconnect_resets_fifo_and_old_generation_is_not_replayed(pipewire_socket):
    connection = WPConnection()
    first = capture_runtime_snapshot(connection)
    assert dispatch_runtime_mutation(
        connection, _request(generation=first.generation)
    ).dispatch_order == 1

    generation = connection.reconnect()
    stale = dispatch_runtime_mutation(
        connection,
        _request(request_id="old", generation=first.generation),
    )
    current = dispatch_runtime_mutation(
        connection,
        _request(request_id="current", generation=generation),
    )

    assert stale.disposition is MutationDispatchDisposition.REJECTED
    assert stale.failure_code is MutationFailureCode.STALE_GENERATION
    assert current.disposition is MutationDispatchDisposition.REJECTED
    assert current.failure_code is MutationFailureCode.TARGET_NOT_FOUND
    assert current.dispatch_order == 1


def test_shutdown_releases_dispatch_as_structured_cancellation(pipewire_socket):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    connection.stop()

    ticket = dispatch_runtime_mutation(
        connection,
        _request(generation=snapshot.generation),
    )

    assert ticket.disposition is MutationDispatchDisposition.CANCELLED
    assert ticket.failure_code is MutationFailureCode.RUNTIME_STOPPED
    assert ticket.dispatch_order == 0
