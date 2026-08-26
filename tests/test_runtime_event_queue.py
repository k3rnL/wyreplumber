from queue import Queue
from threading import Thread

import pytest

from wyreplumber.runtime import (
    NodeValue,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeEventQueue,
    RuntimeEventQueueClosed,
    RuntimeEventQueueEmpty,
    RuntimeEventQueueResnapshotRequired,
    RuntimeObjectKind,
)


def event(sequence, *, generation=4):
    return RuntimeEvent(
        generation=generation,
        sequence=sequence,
        occurred_at="2026-08-22T15:00:00Z",
        kind=RuntimeEventKind.OBJECT_CHANGED,
        object_kind=RuntimeObjectKind.NODE,
        object_id=20,
        current=NodeValue(id=20, name=f"node-{sequence}"),
    )


def test_queue_delivers_events_in_publication_order():
    events = RuntimeEventQueue(3, generation=4, sequence=10)

    assert events.publish(event(11))
    assert events.publish(event(12))

    assert events.get_nowait().sequence == 11
    assert events.get_nowait().sequence == 12
    with pytest.raises(RuntimeEventQueueEmpty):
        events.get_nowait()


def test_blocking_consumer_is_released_by_an_event():
    events = RuntimeEventQueue(2, generation=4, sequence=10)
    received = Queue()
    consumer = Thread(target=lambda: received.put(events.get(timeout=1)), daemon=True)

    consumer.start()
    assert events.publish(event(11))
    consumer.join(timeout=1)

    assert not consumer.is_alive()
    assert received.get_nowait().sequence == 11


def test_timeout_and_non_blocking_reads_report_empty():
    events = RuntimeEventQueue(2, generation=4, sequence=10)

    with pytest.raises(RuntimeEventQueueEmpty):
        events.get(timeout=0.001)
    with pytest.raises(ValueError, match="timeout"):
        events.get(block=False, timeout=0)


def test_overflow_replaces_buffer_with_one_discontinuity_until_reset():
    events = RuntimeEventQueue(2, generation=4, sequence=10)
    events.publish(event(11))
    events.publish(event(12))

    assert events.publish(event(13))
    assert events.requires_resnapshot
    assert events.qsize() == 1

    discontinuity = events.get_nowait()
    assert discontinuity.kind is RuntimeEventKind.DISCONTINUITY
    assert discontinuity.sequence == 13
    assert discontinuity.reason == "event queue capacity 2 exceeded"
    assert not events.publish(event(14))

    with pytest.raises(RuntimeEventQueueResnapshotRequired) as error:
        events.get_nowait()
    assert error.value.generation == 4
    assert error.value.sequence == 13

    events.reset(generation=4, sequence=20)
    assert events.publish(event(21))
    assert events.get_nowait().sequence == 21


@pytest.mark.parametrize(
    ("next_event", "reason"),
    (
        (event(12), "expected event sequence 11, received 12"),
        (event(1, generation=5), "connection generation changed from 4 to 5"),
    ),
)
def test_ordering_loss_becomes_an_explicit_discontinuity(next_event, reason):
    events = RuntimeEventQueue(2, generation=4, sequence=10)

    assert events.publish(next_event)

    discontinuity = events.get_nowait()
    assert discontinuity.requires_resnapshot
    assert discontinuity.reason == reason


def test_published_resnapshot_event_discards_older_deltas():
    events = RuntimeEventQueue(2, generation=4, sequence=10)
    events.publish(event(11))
    resnapshot = RuntimeEvent.discontinuity(
        generation=4,
        sequence=12,
        occurred_at="2026-08-22T15:00:01Z",
        reason="native extraction failed",
    )

    assert events.publish(resnapshot)
    assert events.get_nowait() is resnapshot


def test_close_drains_buffer_then_releases_waiters_and_rejects_publication():
    events = RuntimeEventQueue(2, generation=4, sequence=10)
    events.publish(event(11))
    events.close()

    assert events.get_nowait().sequence == 11
    with pytest.raises(RuntimeEventQueueClosed):
        events.get()
    assert not events.publish(event(12))
    with pytest.raises(RuntimeEventQueueClosed):
        events.reset(generation=4, sequence=12)


def test_close_releases_a_blocked_consumer():
    events = RuntimeEventQueue(2, generation=4, sequence=10)
    outcome = Queue()

    def consume():
        try:
            events.get()
        except Exception as error:  # noqa: BLE001 - asserting the cross-thread outcome
            outcome.put(error)

    consumer = Thread(target=consume, daemon=True)
    consumer.start()
    events.close()
    consumer.join(timeout=1)

    assert not consumer.is_alive()
    assert isinstance(outcome.get_nowait(), RuntimeEventQueueClosed)
