from queue import Queue
from threading import Thread

import pytest

from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    ConnectionState,
    RuntimeContinuityError,
    RuntimeEventKind,
    RuntimeObjectKind,
    capture_runtime_snapshot,
    drain_runtime_events,
    next_runtime_event,
    require_event_continuity,
)


def test_reconnect_changes_generation_and_restarts_monotonic_sequences(
    pipewire_socket,
):
    connection = WPConnection()
    first = capture_runtime_snapshot(connection)

    generation = connection.reconnect()
    lifecycle = drain_runtime_events(connection)

    assert generation == first.generation + 1
    disconnected = next(
        event
        for event in lifecycle
        if event.kind is RuntimeEventKind.CONNECTION_CHANGED
        and event.current.state is ConnectionState.DISCONNECTED
    )
    connected = next(
        event
        for event in lifecycle
        if event.kind is RuntimeEventKind.CONNECTION_CHANGED
        and event.current.state is ConnectionState.CONNECTED
        and event.generation == generation
    )
    assert disconnected.generation == first.generation
    assert connected.sequence == 1

    by_generation = {}
    for event in lifecycle:
        by_generation.setdefault(event.generation, []).append(event.sequence)
    for sequences in by_generation.values():
        assert sequences == sorted(sequences)
        assert len(sequences) == len(set(sequences))

    with pytest.raises(RuntimeContinuityError) as error:
        require_event_continuity(
            connected,
            generation=first.generation,
            sequence=disconnected.sequence,
        )
    assert error.value.code == "generation_changed"

    second = capture_runtime_snapshot(connection)
    assert second.generation == generation
    assert second.sequence == connected.sequence + 1


def test_stop_releases_a_native_waiter_and_is_terminal(pipewire_socket):
    connection = WPConnection()
    snapshot = capture_runtime_snapshot(connection)
    outcome = Queue()

    def wait_for_event():
        try:
            outcome.put(next_runtime_event(connection))
        except Exception as error:  # noqa: BLE001 - asserting cross-thread release
            outcome.put(error)

    waiter = Thread(target=wait_for_event, daemon=True)
    waiter.start()
    connection.stop()
    waiter.join(timeout=2)

    assert not waiter.is_alive()
    stopped = outcome.get_nowait()
    assert stopped.kind is RuntimeEventKind.CONNECTION_CHANGED
    assert stopped.object_kind is RuntimeObjectKind.CONNECTION
    assert stopped.current.state is ConnectionState.STOPPED
    assert stopped.generation == snapshot.generation
    assert stopped.sequence == snapshot.sequence + 1

    with pytest.raises(RuntimeError, match="closed"):
        next_runtime_event(connection, block=False)
    with pytest.raises(RuntimeError, match="not ready"):
        capture_runtime_snapshot(connection)
    with pytest.raises(RuntimeError, match="Invalid WPConnection"):
        connection.sync()

    connection.stop()
