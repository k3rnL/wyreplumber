import base64
import json
import os
import subprocess
import tempfile
import wave
from time import monotonic

import pytest

from wyreplumber import spa_pod
from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    ConfirmationOperator,
    ConfirmationPredicateValue,
    MutationDispatchDisposition,
    MutationFailureCode,
    MutationOperation,
    MutationRequest,
    MutationStatus,
    MutationTargetValue,
    RuntimeObjectKind,
    capture_runtime_snapshot,
    clear_default_node,
    clear_runtime_metadata,
    clear_stream_target,
    dispatch_runtime_mutation,
    set_default_node,
    set_runtime_metadata,
    set_stream_target,
)


def _default_metadata(snapshot):
    return next(item for item in snapshot.metadata if item.name == "default")


def _entry(snapshot, metadata_id, subject, key):
    metadata = snapshot.metadata_by_id[metadata_id]
    return next(
        (
            item
            for item in reversed(metadata.entries)
            if item.subject == subject and item.key == key
        ),
        None,
    )


def _unsupported_request(generation, metadata_id):
    target = MutationTargetValue(
        object_kind=RuntimeObjectKind.NODE,
        object_id=999_999,
        selector={"parameter_id": "Props"},
    )
    return MutationRequest.create(
        request_id="unsupported-after-metadata-controls",
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


def _loopback_nodes(connection):
    module = connection.load_module(
        "libpipewire-module-loopback",
        arguments=json.dumps(
            {
                "capture.props": {
                    "node.name": "metadata_control_sink",
                    "media.class": "Audio/Sink",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
                "playback.props": {
                    "node.name": "metadata_control_stream",
                    "media.class": "Stream/Output/Audio",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
            }
        ),
    )
    deadline = monotonic() + 4
    while monotonic() < deadline:
        snapshot = capture_runtime_snapshot(connection)
        sink = next(
            (item for item in snapshot.nodes if item.name == "metadata_control_sink"),
            None,
        )
        stream = next(
            (item for item in snapshot.nodes if item.name == "metadata_control_stream"),
            None,
        )
        if sink is not None and stream is not None:
            return module, snapshot, sink, stream
        connection.sync()
    pytest.fail("controlled sink and stream nodes did not appear")


def _controlled_sink(connection, name):
    module = connection.load_module(
        "libpipewire-module-loopback",
        arguments=json.dumps(
            {
                "capture.props": {
                    "node.name": name,
                    "media.class": "Audio/Sink",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
                "playback.props": {
                    "node.name": f"{name}_fixture_playback",
                    "media.class": "Stream/Output/Audio",
                    "audio.channels": 2,
                    "audio.position": "FL,FR",
                },
            }
        ),
    )
    deadline = monotonic() + 4
    while monotonic() < deadline:
        snapshot = capture_runtime_snapshot(connection)
        sink = next((node for node in snapshot.nodes if node.name == name), None)
        if sink is not None:
            return module, snapshot, sink
        connection.sync()
    pytest.fail(f"controlled sink {name!r} did not appear")


def _wait_for_stream_route(connection, stream_id, sink_id, *, absent_sink_id=None):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        snapshot = capture_runtime_snapshot(connection)
        links = [
            link for link in snapshot.links if link.output_node_id == stream_id
        ]
        if any(link.input_node_id == sink_id for link in links) and (
            absent_sink_id is None
            or all(link.input_node_id != absent_sink_id for link in links)
        ):
            return snapshot, links
        connection.sync()
    pytest.fail(
        f"stream {stream_id} did not converge to sink {sink_id} through policy"
    )


def test_generic_metadata_set_clear_is_confirmed_idempotent_and_key_scoped(
    pipewire_socket,
):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    metadata = _default_metadata(snapshot)
    subject = 0

    preserved = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=subject,
        key="open-cinema.preserve",
        type_name="Spa:String",
        value="preserved",
        expected_generation=snapshot.generation,
        request_id="set-preserved-entry",
    )
    set_target = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=subject,
        key="target.object",
        type_name="Spa:Id",
        value="1234",
        expected_generation=snapshot.generation,
        request_id="set-target-entry",
    )
    idempotent = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=subject,
        key="target.object",
        type_name="Spa:Id",
        value="1234",
        expected_generation=snapshot.generation,
        request_id="same-target-entry",
    )
    cleared = clear_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=subject,
        key="target.object",
        expected_generation=snapshot.generation,
        request_id="clear-target-entry",
    )
    final = capture_runtime_snapshot(connection)
    next_ticket = dispatch_runtime_mutation(
        connection, _unsupported_request(snapshot.generation, metadata.id)
    )

    assert preserved.status is MutationStatus.CONFIRMED
    assert set_target.status is MutationStatus.CONFIRMED
    assert idempotent.status is MutationStatus.CONFIRMED
    assert cleared.status is MutationStatus.CONFIRMED
    assert _entry(final, metadata.id, subject, "target.object") is None
    assert _entry(final, metadata.id, subject, "open-cinema.preserve").value == "preserved"
    assert next_ticket.disposition is MutationDispatchDisposition.REJECTED
    assert next_ticket.failure_code is MutationFailureCode.TARGET_NOT_FOUND
    assert next_ticket.dispatch_order == 4


def test_default_node_preference_is_observed_and_cleared_independently(pipewire_socket):
    connection = WPConnection()
    module, snapshot, sink, _ = _loopback_nodes(connection)
    metadata = _default_metadata(snapshot)
    preserved = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=0,
        key="default.configured.audio.source",
        type_name="Spa:String:JSON",
        value='{"name":"leave-this-source"}',
        expected_generation=snapshot.generation,
    )
    resolved = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=0,
        key="default.audio.sink",
        type_name="Spa:String:JSON",
        value=json.dumps({"name": sink.name}, separators=(",", ":")),
        expected_generation=snapshot.generation,
    )

    selected = set_default_node(
        connection,
        node_id=sink.id,
        expected_generation=snapshot.generation,
        request_id="set-default-sink",
    )
    observed = capture_runtime_snapshot(connection)
    cleared = clear_default_node(
        connection,
        media_class="Audio/Sink",
        expected_generation=snapshot.generation,
        request_id="clear-default-sink",
    )
    final = capture_runtime_snapshot(connection)

    assert module is not None
    assert preserved.status is MutationStatus.CONFIRMED
    assert resolved.status is MutationStatus.CONFIRMED
    assert selected.status is MutationStatus.CONFIRMED
    assert observed.defaults.audio_sink.configured_name == sink.name
    assert observed.defaults.audio_sink.resolved_node_id == sink.id
    assert cleared.status is MutationStatus.CONFIRMED
    assert _entry(
        final, metadata.id, 0, "default.configured.audio.sink"
    ) is None
    assert _entry(
        final, metadata.id, 0, "default.configured.audio.source"
    ).value == '{"name":"leave-this-source"}'


def test_stream_target_uses_target_object_and_safe_clear(pipewire_socket):
    connection = WPConnection()
    module, snapshot, sink, stream = _loopback_nodes(connection)
    metadata = _default_metadata(snapshot)
    preserved = set_runtime_metadata(
        connection,
        metadata_id=metadata.id,
        subject=stream.id,
        key="open-cinema.stream-owner",
        value="test-owner",
        expected_generation=snapshot.generation,
    )

    selected = set_stream_target(
        connection,
        stream_node_id=stream.id,
        target_node_id=sink.id,
        expected_generation=snapshot.generation,
        request_id="set-stream-target",
    )
    targeted = capture_runtime_snapshot(connection)
    cleared = clear_stream_target(
        connection,
        stream_node_id=stream.id,
        expected_generation=snapshot.generation,
        request_id="clear-stream-target",
    )
    final = capture_runtime_snapshot(connection)

    target_entry = _entry(targeted, metadata.id, stream.id, "target.object")
    assert module is not None
    assert preserved.status is MutationStatus.CONFIRMED
    assert selected.status is MutationStatus.CONFIRMED
    assert target_entry is not None
    assert target_entry.type_name in {"Spa:Id", "Spa:String"}
    assert cleared.status is MutationStatus.CONFIRMED
    assert _entry(final, metadata.id, stream.id, "target.object") is None
    assert _entry(
        final, metadata.id, stream.id, "open-cinema.stream-owner"
    ).value == "test-owner"


def test_wireplumber_default_and_target_metadata_move_an_ordinary_stream(
    pipewire_socket,
):
    connection = WPConnection()
    main_module, snapshot, main_sink = _controlled_sink(
        connection,
        "routing_policy_main_sink",
    )
    headset_module, snapshot, headset_sink = _controlled_sink(
        connection,
        "routing_policy_headset_sink",
    )
    selected_default = set_default_node(
        connection,
        node_id=main_sink.id,
        expected_generation=snapshot.generation,
        timeout=4,
    )
    process_env = os.environ.copy()
    process_env.pop("PIPEWIRE_CONFIG_DIR", None)
    audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    audio_file.close()
    with wave.open(audio_file.name, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(b"\0" * (48000 * 2 * 2 * 15))
    process = subprocess.Popen(
        [
            "pw-cat",
            "--playback",
            "--rate=48000",
            "--channels=2",
            "--format=s16",
            "--properties={ node.name = routing_policy_program_stream }",
            audio_file.name,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=process_env,
    )
    try:
        deadline = monotonic() + 5
        stream = None
        while monotonic() < deadline:
            snapshot = capture_runtime_snapshot(connection)
            stream = next(
                (
                    node
                    for node in snapshot.nodes
                    if node.name == "routing_policy_program_stream"
                ),
                None,
            )
            if stream is not None:
                break
            if process.poll() is not None:
                pytest.fail(f"pw-cat exited early: {process.stderr.read()}")
            connection.sync()
        else:
            pytest.fail("controlled programme stream did not appear")

        default_snapshot, default_links = _wait_for_stream_route(
            connection,
            stream.id,
            main_sink.id,
        )
        targeted = set_stream_target(
            connection,
            stream_node_id=stream.id,
            target_node_id=headset_sink.id,
            expected_generation=default_snapshot.generation,
            timeout=4,
        )
        _, target_links = _wait_for_stream_route(
            connection,
            stream.id,
            headset_sink.id,
            absent_sink_id=main_sink.id,
        )

        assert main_module is not None
        assert headset_module is not None
        assert selected_default.status is MutationStatus.CONFIRMED
        assert targeted.status is MutationStatus.CONFIRMED
        assert all(link.owner is None for link in (*default_links, *target_links))
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        os.unlink(audio_file.name)


def test_metadata_control_validates_and_reports_missing_native_target(pipewire_socket):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)

    with pytest.raises(ValueError, match="PipeWire ID range"):
        set_runtime_metadata(
            connection,
            metadata_id=2**32,
            subject=0,
            key="test.key",
            value="value",
            expected_generation=snapshot.generation,
        )

    missing = set_runtime_metadata(
        connection,
        metadata_id=999_999,
        subject=0,
        key="test.key",
        value="value",
        expected_generation=snapshot.generation,
        timeout=1,
    )

    assert missing.status is MutationStatus.REJECTED
    assert missing.failure.code is MutationFailureCode.TARGET_NOT_FOUND
