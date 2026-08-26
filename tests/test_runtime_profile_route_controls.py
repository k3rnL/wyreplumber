import base64

import pytest

from wyreplumber import spa_pod
from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    Availability,
    ConfirmationOperator,
    ConfirmationPredicateValue,
    ConnectionHealthValue,
    ConnectionState,
    DeviceValue,
    MutationDispatchDisposition,
    MutationDispatchTicketValue,
    MutationFailureCode,
    MutationOperation,
    MutationRequest,
    MutationStatus,
    MutationTargetValue,
    PortDirection,
    ProfileValue,
    RouteValue,
    RuntimeObjectKind,
    RuntimeSnapshot,
    capture_runtime_snapshot,
    dispatch_runtime_mutation,
    select_device_profile,
    select_device_route,
)
from wyreplumber.runtime import controls


def _profile(*, name="analog-stereo", available=Availability.YES, active=False):
    return ProfileValue(
        device_id=10,
        index=1,
        name=name,
        available=available,
        active=active,
        classes=("Audio/Sink",),
    )


def _route(
    *,
    name="speaker",
    available=Availability.YES,
    active=False,
    volume=0.25,
    mute=False,
    channel_volumes=(0.25, 0.25),
):
    return RouteValue(
        device_id=10,
        index=2,
        direction=PortDirection.OUTPUT,
        name=name,
        available=available,
        active=active,
        profile_ids=(1,),
        volume=volume,
        mute=mute,
        channel_volumes=channel_volumes,
        properties={"spa_device_index": 0},
    )


def _snapshot(*, sequence, profile=None, route=None):
    profiles = () if profile is None else (profile,)
    routes = () if route is None else (route,)
    return RuntimeSnapshot(
        generation=7,
        sequence=sequence,
        captured_at=f"2026-08-22T12:00:{sequence:02d}Z",
        health=ConnectionHealthValue(
            state=ConnectionState.CONNECTED,
            generation=7,
        ),
        devices=(
            DeviceValue(
                id=10,
                name="test-card",
                parameter_ids=("EnumProfile", "Profile", "EnumRoute", "Route"),
                profile_ids=tuple(item.index for item in profiles),
                route_ids=tuple(item.index for item in routes),
            ),
        ),
        profiles=profiles,
        routes=routes,
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
            dispatch_order=1,
            disposition=MutationDispatchDisposition.READY,
            expected_generation=request.expected_generation,
            expected_sequence=request.expected_sequence,
            observed_generation=request.expected_generation,
            observed_sequence=preflight.sequence,
        )

    monkeypatch.setattr(controls, "dispatch_runtime_mutation", dispatch)
    return dispatched


def test_profile_selection_validates_identity_and_confirms_active(monkeypatch):
    selected = _profile(active=False)
    preflight = _snapshot(sequence=1, profile=selected)
    confirmed = _snapshot(sequence=2, profile=_profile(active=True))
    dispatched = _install_confirming_runtime(monkeypatch, preflight, confirmed)

    outcome = select_device_profile(
        object(),
        profile=selected,
        expected_generation=7,
        request_id="select-profile",
    )
    pod = spa_pod.parse_spa_pod(
        base64.b64decode(dispatched[0].payload["pod_base64"])
    )

    assert outcome.status is MutationStatus.CONFIRMED
    assert outcome.operation is MutationOperation.SELECT_PROFILE
    assert len(outcome.confirmations) == 2
    assert isinstance(pod, spa_pod.SpaParamProfile)
    assert pod.index == selected.index


def test_route_selection_writes_props_and_confirms_one_coherent_route(monkeypatch):
    selected = _route(active=False)
    preflight = _snapshot(
        sequence=1,
        profile=_profile(active=True),
        route=selected,
    )
    confirmed = _snapshot(
        sequence=2,
        profile=_profile(active=True),
        route=_route(
            active=True,
            volume=0.6000000238418579,
            mute=True,
            channel_volumes=(0.6000000238418579, 0.5),
        ),
    )
    dispatched = _install_confirming_runtime(monkeypatch, preflight, confirmed)

    outcome = select_device_route(
        object(),
        route=selected,
        expected_generation=7,
        volume=0.6,
        mute=True,
        channel_volumes=(0.6, 0.5),
        request_id="select-route",
    )
    pod = spa_pod.parse_spa_pod(
        base64.b64decode(dispatched[0].payload["pod_base64"])
    )

    assert outcome.status is MutationStatus.CONFIRMED
    assert outcome.operation is MutationOperation.SELECT_ROUTE
    assert len(outcome.confirmations) == 5
    assert isinstance(pod, spa_pod.SpaParamRoute)
    assert pod.index == selected.index
    assert pod.device == 0
    assert pod.save is True
    assert pod.props.mute is True
    assert pod.props.channelVolumes == pytest.approx([0.6, 0.5])


def test_unavailable_profile_is_rejected_without_native_dispatch(monkeypatch):
    unavailable = _profile(available=Availability.NO)
    preflight = _snapshot(sequence=1, profile=unavailable)
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: preflight)
    monkeypatch.setattr(
        controls,
        "dispatch_runtime_mutation",
        lambda *args: pytest.fail("unavailable profile reached native dispatch"),
    )

    outcome = select_device_profile(
        object(),
        profile=unavailable,
        expected_generation=7,
    )

    assert outcome.status is MutationStatus.REJECTED
    assert outcome.failure.code is MutationFailureCode.TARGET_UNAVAILABLE


def test_stale_route_identity_is_rejected_without_native_dispatch(monkeypatch):
    requested = _route(name="speaker")
    current = _route(name="headphones")
    preflight = _snapshot(
        sequence=1,
        profile=_profile(active=True),
        route=current,
    )
    monkeypatch.setattr(controls, "_capture_snapshot", lambda connection: preflight)
    monkeypatch.setattr(
        controls,
        "dispatch_runtime_mutation",
        lambda *args: pytest.fail("stale route reached native dispatch"),
    )

    outcome = select_device_route(
        object(),
        route=requested,
        expected_generation=7,
    )

    assert outcome.status is MutationStatus.REJECTED
    assert outcome.failure.code is MutationFailureCode.TARGET_IDENTITY_CHANGED


def test_route_properties_validate_before_snapshot_or_native(monkeypatch):
    monkeypatch.setattr(
        controls,
        "_capture_snapshot",
        lambda *args: pytest.fail("invalid route property reached runtime preflight"),
    )

    with pytest.raises(TypeError, match="mute"):
        select_device_route(
            object(),
            route=_route(),
            expected_generation=7,
            mute=1,
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        select_device_route(
            object(),
            route=_route(),
            expected_generation=7,
            volume=-0.1,
        )


@pytest.mark.parametrize(
    ("operation", "parameter_id", "value"),
    (
        (
            MutationOperation.SELECT_PROFILE,
            "Profile",
            spa_pod.SpaParamProfile(index=1),
        ),
        (
            MutationOperation.SELECT_ROUTE,
            "Route",
            spa_pod.SpaParamRoute(index=2, device=0),
        ),
    ),
)
def test_native_profile_and_route_dispatch_report_missing_device(
    pipewire_socket, operation, parameter_id, value
):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.DEVICE,
        object_id=999_999,
        selector={"parameter_id": parameter_id},
    )
    request = MutationRequest.create(
        expected_generation=snapshot.generation,
        operation=operation,
        target=target,
        payload={
            "flags": 0,
            "pod_base64": base64.b64encode(spa_pod.build_spa_pod(value)).decode(
                "ascii"
            ),
        },
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.PRESENT,
            ),
        ),
    )

    ticket = dispatch_runtime_mutation(connection, request)

    assert ticket.disposition is MutationDispatchDisposition.REJECTED
    assert ticket.failure_code is MutationFailureCode.TARGET_NOT_FOUND
