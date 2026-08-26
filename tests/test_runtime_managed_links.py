import json
from time import monotonic

import pytest

from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    ConfirmationOperator,
    ConfirmationPredicateValue,
    ConnectionHealthValue,
    ConnectionState,
    LinkValue,
    MutationDispatchDisposition,
    MutationDispatchTicketValue,
    MutationFailureCode,
    MutationOperation,
    MutationRequest,
    MutationStatus,
    MutationTargetValue,
    NodeValue,
    PortDirection,
    PortValue,
    RuntimeObjectKind,
    RuntimeSnapshot,
    capture_runtime_snapshot,
    create_managed_link,
    dispatch_runtime_mutation,
    remove_managed_link,
)
from wyreplumber.runtime import controls


ENDPOINTS = {
    "output_node_id": 1,
    "output_port_id": 11,
    "input_node_id": 2,
    "input_port_id": 21,
}


def _link(*, link_id=30, owner="test.owner", desired_id="front-left", **changes):
    values = {
        "id": link_id,
        **ENDPOINTS,
        "state": "active",
        "owner": owner,
        "desired_id": desired_id,
        "properties": {
            "open-cinema.owner": owner,
            "open-cinema.desired-id": desired_id,
        }
        if owner is not None and desired_id is not None
        else {},
    }
    values.update(changes)
    return LinkValue(**values)


def _snapshot(*, sequence, links=()):
    return RuntimeSnapshot(
        generation=9,
        sequence=sequence,
        captured_at=f"2026-08-22T12:00:{sequence:02d}Z",
        health=ConnectionHealthValue(
            state=ConnectionState.CONNECTED,
            generation=9,
        ),
        nodes=(
            NodeValue(id=1, name="source", output_port_ids=(11,)),
            NodeValue(id=2, name="sink", input_port_ids=(21,)),
        ),
        ports=(
            PortValue(id=11, node_id=1, direction=PortDirection.OUTPUT),
            PortValue(id=21, node_id=2, direction=PortDirection.INPUT),
        ),
        links=tuple(links),
    )


def _install_confirming_runtime(monkeypatch, preflight, confirmed):
    snapshots = iter((preflight, confirmed))
    dispatched = []
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: next(snapshots))

    def dispatch(connection, request):
        dispatched.append(request)
        return MutationDispatchTicketValue(
            request_id=request.request_id,
            operation=request.operation,
            dispatch_order=len(dispatched),
            disposition=MutationDispatchDisposition.READY,
            expected_generation=request.expected_generation,
            expected_sequence=request.expected_sequence,
            observed_generation=request.expected_generation,
            observed_sequence=preflight.sequence,
        )

    monkeypatch.setattr(controls, "dispatch_runtime_mutation", dispatch)
    return dispatched


def test_managed_link_create_and_remove_confirm_owned_observation(monkeypatch):
    managed = _link()
    create_dispatches = _install_confirming_runtime(
        monkeypatch,
        _snapshot(sequence=1),
        _snapshot(sequence=2, links=(managed,)),
    )

    created = create_managed_link(
        object(),
        owner="test.owner",
        desired_id="front-left",
        expected_generation=9,
        passive=True,
        properties={"link.group": "test-group"},
        **ENDPOINTS,
    )

    assert created.status is MutationStatus.CONFIRMED
    assert created.operation is MutationOperation.CREATE_LINK
    assert create_dispatches[0].payload["properties"] == {
        "link.group": "test-group",
        "link.passive": "true",
    }

    remove_dispatches = _install_confirming_runtime(
        monkeypatch,
        _snapshot(sequence=3, links=(managed,)),
        _snapshot(sequence=4),
    )
    removed = remove_managed_link(
        object(),
        owner="test.owner",
        desired_id="front-left",
        expected_generation=9,
    )

    assert removed.status is MutationStatus.CONFIRMED
    assert removed.operation is MutationOperation.REMOVE_LINK
    assert remove_dispatches[0].payload["link_id"] == managed.id


def test_existing_owned_link_is_idempotent_without_native_dispatch(monkeypatch):
    snapshot = _snapshot(sequence=1, links=(_link(),))
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: snapshot)
    monkeypatch.setattr(
        controls,
        "dispatch_runtime_mutation",
        lambda *args: pytest.fail("idempotent managed link reached native dispatch"),
    )

    outcome = create_managed_link(
        object(),
        owner="test.owner",
        desired_id="front-left",
        expected_generation=9,
        **ENDPOINTS,
    )

    assert outcome.status is MutationStatus.CONFIRMED


@pytest.mark.parametrize(
    "conflicting_link",
    (
        _link(owner=None, desired_id=None),
        _link(input_node_id=3, input_port_id=31),
    ),
)
def test_unmanaged_topology_or_reused_identity_is_a_conflict(
    monkeypatch, conflicting_link
):
    extra_nodes = ()
    extra_ports = ()
    if conflicting_link.input_node_id == 3:
        extra_nodes = (NodeValue(id=3, name="other", input_port_ids=(31,)),)
        extra_ports = (
            PortValue(id=31, node_id=3, direction=PortDirection.INPUT),
        )
    base = _snapshot(sequence=1, links=())
    snapshot = RuntimeSnapshot(
        generation=base.generation,
        sequence=base.sequence,
        captured_at=base.captured_at,
        health=base.health,
        nodes=base.nodes + extra_nodes,
        ports=base.ports + extra_ports,
        links=(conflicting_link,),
    )
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: snapshot)
    monkeypatch.setattr(
        controls,
        "dispatch_runtime_mutation",
        lambda *args: pytest.fail("conflicting link reached native dispatch"),
    )

    outcome = create_managed_link(
        object(),
        owner="test.owner",
        desired_id="front-left",
        expected_generation=9,
        **ENDPOINTS,
    )

    assert outcome.status is MutationStatus.REJECTED
    assert outcome.failure.code is MutationFailureCode.OWNERSHIP_CONFLICT


def test_remove_absent_managed_identity_never_removes_unmanaged_link(monkeypatch):
    unmanaged = _link(owner=None, desired_id=None)
    snapshot = _snapshot(sequence=1, links=(unmanaged,))
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: snapshot)
    monkeypatch.setattr(
        controls,
        "dispatch_runtime_mutation",
        lambda *args: pytest.fail("absent managed identity reached native dispatch"),
    )

    outcome = remove_managed_link(
        object(),
        owner="test.owner",
        desired_id="front-left",
        expected_generation=9,
    )

    assert outcome.status is MutationStatus.CONFIRMED
    assert snapshot.links == (unmanaged,)


def _runtime_link_endpoints(connection):
    modules = []
    for suffix in ("a", "b"):
        modules.append(
            connection.load_module(
                "libpipewire-module-loopback",
                arguments=json.dumps(
                    {
                        "capture.props": {
                            "node.name": f"managed_link_sink_{suffix}",
                            "media.class": "Audio/Sink",
                            "audio.channels": 1,
                            "audio.position": "MONO",
                        },
                        "playback.props": {
                            "node.name": f"managed_link_stream_{suffix}",
                            "media.class": "Stream/Output/Audio",
                            "audio.channels": 1,
                            "audio.position": "MONO",
                        },
                    }
                ),
            )
        )
    deadline = monotonic() + 5
    while monotonic() < deadline:
        snapshot = capture_runtime_snapshot(connection)
        streams = [
            node
            for node in snapshot.nodes
            if node.name and node.name.startswith("managed_link_stream_")
        ]
        sinks = [
            node
            for node in snapshot.nodes
            if node.name and node.name.startswith("managed_link_sink_")
        ]
        for stream in streams:
            for sink in sinks:
                for output_port_id in stream.output_port_ids:
                    for input_port_id in sink.input_port_ids:
                        endpoints = {
                            "output_node_id": stream.id,
                            "output_port_id": output_port_id,
                            "input_node_id": sink.id,
                            "input_port_id": input_port_id,
                        }
                        if not any(
                            all(getattr(link, key) == value for key, value in endpoints.items())
                            for link in snapshot.links
                        ):
                            return modules, snapshot, endpoints
        connection.sync()
    pytest.fail("no unlinked controlled output/input port pair appeared")


def test_native_managed_link_lifecycle_is_confirmed(pipewire_socket):
    connection = WPConnection()
    modules, snapshot, endpoints = _runtime_link_endpoints(connection)

    created = create_managed_link(
        connection,
        owner="wyreplumber.tests",
        desired_id="native-managed-link",
        expected_generation=snapshot.generation,
        timeout=3,
        **endpoints,
    )
    observed = capture_runtime_snapshot(connection)
    assert created.status is MutationStatus.CONFIRMED
    managed = next(
        link
        for link in observed.links
        if link.owner == "wyreplumber.tests"
        and link.desired_id == "native-managed-link"
    )
    wrong_target = MutationTargetValue(
        object_kind=RuntimeObjectKind.LINK,
        object_id="wrong-link",
        selector={"owner": "someone.else", "desired_id": "wrong-link"},
    )
    wrong_remove = dispatch_runtime_mutation(
        connection,
        MutationRequest.create(
            expected_generation=snapshot.generation,
            operation=MutationOperation.REMOVE_LINK,
            target=wrong_target,
            payload={"link_id": managed.id},
            confirmation_predicates=(
                ConfirmationPredicateValue(
                    target=wrong_target,
                    operator=ConfirmationOperator.ABSENT,
                ),
            ),
        ),
    )
    still_present = capture_runtime_snapshot(connection)
    removed = remove_managed_link(
        connection,
        owner="wyreplumber.tests",
        desired_id="native-managed-link",
        expected_generation=snapshot.generation,
        timeout=3,
    )
    final = capture_runtime_snapshot(connection)

    assert len(modules) == 2
    assert all(getattr(managed, key) == value for key, value in endpoints.items())
    assert wrong_remove.disposition is MutationDispatchDisposition.REJECTED
    assert wrong_remove.failure_code is MutationFailureCode.OWNERSHIP_CONFLICT
    assert managed.id in still_present.links_by_id
    assert removed.status is MutationStatus.CONFIRMED
    assert all(link.id != managed.id for link in final.links)
