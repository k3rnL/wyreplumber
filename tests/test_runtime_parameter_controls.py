import base64
import json
import os
import subprocess
from time import monotonic

import pytest

from wyreplumber import spa_pod
from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    AudioPropertiesValue,
    ConfirmationOperator,
    ConfirmationPredicateValue,
    MutationDispatchDisposition,
    MutationFailureCode,
    MutationOperation,
    MutationRequest,
    MutationStatus,
    MutationTargetValue,
    NodeState,
    RuntimeObjectKind,
    capture_runtime_snapshot,
    dispatch_runtime_mutation,
    set_node_audio_properties,
    set_node_mute,
    set_node_volume,
    set_runtime_parameter,
)


def _stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _loopback_node(connection, request):
    module = connection.load_module(
        "libpipewire-module-loopback",
        arguments=json.dumps(
            {
                "capture.props": {
                    "node.name": "runtime_control_sink",
                    "media.class": "Audio/Sink",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
                "playback.props": {
                    "node.name": "runtime_control_playback",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
            }
        ),
    )
    deadline = monotonic() + 4
    while monotonic() < deadline:
        snapshot = capture_runtime_snapshot(connection)
        node = next(
            (item for item in snapshot.nodes if item.name == "runtime_control_sink"),
            None,
        )
        if node is not None:
            parameter = snapshot.parameters_by_key.get(("node", node.id, "Props"))
            if parameter and parameter.values:
                break
        connection.sync()
    else:
        pytest.fail("controlled loopback node with readable Props did not appear")

    player_env = dict(os.environ)
    player_env.pop("PIPEWIRE_CONFIG_DIR", None)
    player_command = ["pw-cat", "--playback"]
    player_help = subprocess.run(
        ["pw-cat", "--help"],
        capture_output=True,
        text=True,
        env=player_env,
        check=False,
    )
    if "--raw" in player_help.stdout:
        player_command.append("--raw")
    player_command.extend(
        [
            "--target",
            "runtime_control_sink",
            "--rate",
            "48000",
            "--channels",
            "2",
            "--format",
            "s16",
            "-",
        ]
    )
    zero_stream = open("/dev/zero", "rb")
    try:
        player = subprocess.Popen(
            player_command,
            stdin=zero_stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=player_env,
        )
    finally:
        zero_stream.close()
    request.addfinalizer(lambda: _stop_process(player))
    node_id = node.id
    deadline = monotonic() + 4
    while monotonic() < deadline:
        if player.poll() is not None:
            pytest.fail(
                f"test audio stream exited with status {player.returncode}: "
                f"{player.stderr.read().strip()}"
            )
        snapshot = capture_runtime_snapshot(connection)
        node = snapshot.nodes_by_id.get(node_id)
        parameter = snapshot.parameters_by_key.get(("node", node_id, "Props"))
        if (
            node is not None
            and node.state is NodeState.RUNNING
            and parameter
            and parameter.values
        ):
            return module, snapshot, node, parameter
        connection.sync()
    pytest.fail("controlled loopback node did not become active")


def _unsupported_request(generation, node_id):
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=node_id,
        selector={"parameter_id": "EnumFormat"},
    )
    return MutationRequest.create(
        request_id="unsupported-after-idempotency",
        expected_generation=generation,
        operation=MutationOperation.SET_PARAMETER,
        target=target,
        payload={
            "flags": 0,
            "pod_base64": base64.b64encode(
                spa_pod.build_spa_pod(spa_pod.SpaProps(mute=False))
            ).decode("ascii"),
        },
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.PRESENT,
            ),
        ),
        timeout=2,
    )


def test_typed_volume_and_mute_are_confirmed_and_idempotent(
    pipewire_socket, request
):
    connection = WPConnection()
    module, snapshot, node, parameter = _loopback_node(connection, request)
    current = next(
        value for value in parameter.values if isinstance(value, AudioPropertiesValue)
    )
    requested_mute = not bool(current.mute)
    requested_volume = 0.42

    outcome = set_node_audio_properties(
        connection,
        node_id=node.id,
        expected_generation=snapshot.generation,
        mute=requested_mute,
        volume=requested_volume,
        timeout=3,
        request_id="set-audio-properties",
    )
    idempotent = set_node_audio_properties(
        connection,
        node_id=node.id,
        expected_generation=snapshot.generation,
        mute=requested_mute,
        volume=requested_volume,
        timeout=3,
        request_id="same-audio-properties",
    )
    next_ticket = dispatch_runtime_mutation(
        connection, _unsupported_request(snapshot.generation, node.id)
    )

    assert module is not None
    assert outcome.status is MutationStatus.CONFIRMED
    assert outcome.succeeded
    assert len(outcome.confirmations) == 2
    assert idempotent.status is MutationStatus.CONFIRMED
    assert next_ticket.disposition is MutationDispatchDisposition.REJECTED
    assert next_ticket.failure_code is MutationFailureCode.NOT_WRITABLE
    assert next_ticket.dispatch_order == 2


def test_typed_volume_and_mute_helpers_validate_before_native_dispatch(
    pipewire_socket, request
):
    connection = WPConnection()
    module, snapshot, node, _ = _loopback_node(connection, request)

    with pytest.raises(TypeError, match="mute"):
        set_node_mute(
            connection,
            node_id=node.id,
            mute=1,
            expected_generation=snapshot.generation,
        )
    with pytest.raises(ValueError, match="finite and non-negative"):
        set_node_volume(
            connection,
            node_id=node.id,
            volume=-0.1,
            expected_generation=snapshot.generation,
        )

    ticket = dispatch_runtime_mutation(
        connection, _unsupported_request(snapshot.generation, node.id)
    )
    assert module is not None
    assert ticket.dispatch_order == 1


def test_effective_mixer_volume_and_mute_are_observed_and_confirmed(
    pipewire_socket, request
):
    connection = WPConnection()
    module, snapshot, node, _ = _loopback_node(connection, request)
    assert snapshot.parameters_by_key.get(("node", node.id, "Mixer")) is not None

    volume = set_node_volume(
        connection,
        node_id=node.id,
        volume=0.42,
        expected_generation=snapshot.generation,
        timeout=3,
        request_id="set-effective-mixer-volume",
    )
    mute = set_node_mute(
        connection,
        node_id=node.id,
        mute=True,
        expected_generation=snapshot.generation,
        timeout=3,
        request_id="set-effective-mixer-mute",
    )
    observed = capture_runtime_snapshot(connection).parameters_by_key[
        ("node", node.id, "Mixer")
    ].values[0]

    assert module is not None
    assert volume.status is MutationStatus.CONFIRMED
    assert volume.operation is MutationOperation.SET_NODE_MIXER
    assert mute.status is MutationStatus.CONFIRMED
    assert observed.volume == pytest.approx(0.42, abs=0.005)
    assert observed.mute is True


def test_generic_parameter_control_reports_stale_target_and_not_writable(
    pipewire_socket, request
):
    connection = WPConnection()
    module, snapshot, node, _ = _loopback_node(connection, request)
    missing_target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=999_999,
        selector={"parameter_id": "Props"},
    )
    missing_predicate = ConfirmationPredicateValue(
        target=missing_target,
        operator=ConfirmationOperator.EQUALS,
        path=("values", 0, "mute"),
        expected=True,
    )
    missing = set_runtime_parameter(
        connection,
        expected_generation=snapshot.generation,
        target_kind=RuntimeObjectKind.NODE,
        target_id=999_999,
        parameter_id="Props",
        value=spa_pod.SpaProps(mute=True),
        confirmation_predicates=(missing_predicate,),
        timeout=1,
    )

    real_target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=node.id,
        selector={"parameter_id": "EnumFormat"},
    )
    not_writable = set_runtime_parameter(
        connection,
        expected_generation=snapshot.generation,
        target_kind=RuntimeObjectKind.NODE,
        target_id=node.id,
        parameter_id="EnumFormat",
        value=spa_pod.SpaProps(mute=True),
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=real_target,
                operator=ConfirmationOperator.EQUALS,
                path=("values", 0, "impossible"),
                expected=True,
            ),
        ),
        timeout=1,
    )

    assert module is not None
    assert missing.status is MutationStatus.REJECTED
    assert missing.failure.code is MutationFailureCode.TARGET_NOT_FOUND
    assert not_writable.status is MutationStatus.REJECTED
    assert not_writable.failure.code is MutationFailureCode.NOT_WRITABLE


def test_generic_parameter_requires_observed_confirmation(pipewire_socket, request):
    connection = WPConnection()
    module, snapshot, node, _ = _loopback_node(connection, request)
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=node.id,
        selector={"parameter_id": "Props"},
    )
    outcome = set_runtime_parameter(
        connection,
        expected_generation=snapshot.generation,
        target_kind=RuntimeObjectKind.NODE,
        target_id=node.id,
        parameter_id="Props",
        value=spa_pod.SpaProps(mute=True),
        confirmation_predicates=(
            ConfirmationPredicateValue(
                target=target,
                operator=ConfirmationOperator.EQUALS,
                path=("values", 0, "mute"),
                expected="impossible",
            ),
        ),
        timeout=0.1,
    )

    assert module is not None
    assert outcome.status is MutationStatus.TIMED_OUT
    assert outcome.failure.code is MutationFailureCode.CONFIRMATION_TIMEOUT
