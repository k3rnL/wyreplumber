"""Bounded thread-safe delivery for detached runtime events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Condition
from time import monotonic

from .events import RuntimeEvent
from .models import _identifier


class RuntimeEventQueueEmpty(Exception):
    """No event is currently available from a non-blocking or timed read."""


class RuntimeEventQueueClosed(RuntimeError):
    """The event queue was closed and has no remaining events."""


class RuntimeEventQueueResnapshotRequired(RuntimeError):
    """Incremental delivery cannot resume until the queue is reset from a snapshot."""

    def __init__(self, *, generation: int, sequence: int, reason: str) -> None:
        self.generation = generation
        self.sequence = sequence
        self.reason = reason
        super().__init__(reason)


class RuntimeEventQueue:
    """Transfer an ordered runtime stream without blocking its native producer.

    ``generation`` and ``sequence`` identify the snapshot from which the consumer
    starts. Publication never waits for capacity. If capacity or continuity is
    lost, queued deltas are replaced by one discontinuity and subsequent events
    are rejected until :meth:`reset` installs a fresh snapshot position.
    """

    def __init__(self, capacity: int, *, generation: int, sequence: int) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("capacity must be an integer")
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        _identifier(generation, "generation")
        _identifier(sequence, "sequence")

        self._capacity = capacity
        self._condition = Condition()
        self._events: deque[RuntimeEvent] = deque()
        self._generation = generation
        self._sequence = sequence
        self._closed = False
        self._resnapshot_required = False
        self._discontinuity_reason: str | None = None

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def generation(self) -> int:
        with self._condition:
            return self._generation

    @property
    def sequence(self) -> int:
        with self._condition:
            return self._sequence

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def requires_resnapshot(self) -> bool:
        with self._condition:
            return self._resnapshot_required

    def qsize(self) -> int:
        with self._condition:
            return len(self._events)

    def publish(self, event: RuntimeEvent) -> bool:
        """Publish immediately, returning false only when the event is rejected."""

        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        with self._condition:
            if self._closed or self._resnapshot_required:
                return False

            if event.generation != self._generation:
                self._invalidate(
                    event,
                    f"connection generation changed from {self._generation} "
                    f"to {event.generation}",
                )
                return True

            expected_sequence = self._sequence + 1
            if event.sequence != expected_sequence:
                self._invalidate(
                    event,
                    f"expected event sequence {expected_sequence}, received {event.sequence}",
                )
                return True

            if event.requires_resnapshot:
                self._events.clear()
                self._events.append(event)
                self._generation = event.generation
                self._sequence = event.sequence
                self._resnapshot_required = True
                self._discontinuity_reason = event.reason or "event requires a new snapshot"
                self._condition.notify_all()
                return True

            if len(self._events) >= self._capacity:
                self._invalidate(event, f"event queue capacity {self._capacity} exceeded")
                return True

            self._events.append(event)
            self._sequence = event.sequence
            self._condition.notify()
            return True

    def get(self, *, block: bool = True, timeout: float | None = None) -> RuntimeEvent:
        """Read the next event, optionally waiting for publication."""

        if not isinstance(block, bool):
            raise TypeError("block must be a boolean")
        if not block and timeout is not None:
            raise ValueError("timeout cannot be used with a non-blocking read")
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise TypeError("timeout must be a number or None")
            if timeout < 0:
                raise ValueError("timeout must be non-negative")

        deadline = None if timeout is None else monotonic() + timeout
        with self._condition:
            while not self._events:
                if self._closed:
                    raise RuntimeEventQueueClosed("event queue is closed")
                if self._resnapshot_required:
                    raise RuntimeEventQueueResnapshotRequired(
                        generation=self._generation,
                        sequence=self._sequence,
                        reason=self._discontinuity_reason
                        or "incremental continuity was lost",
                    )
                if not block:
                    raise RuntimeEventQueueEmpty

                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    raise RuntimeEventQueueEmpty
                self._condition.wait(remaining)

            return self._events.popleft()

    def get_nowait(self) -> RuntimeEvent:
        return self.get(block=False)

    def reset(self, *, generation: int, sequence: int) -> None:
        """Discard pending deltas and establish continuity from a fresh snapshot."""

        _identifier(generation, "generation")
        _identifier(sequence, "sequence")
        with self._condition:
            if self._closed:
                raise RuntimeEventQueueClosed("event queue is closed")
            self._events.clear()
            self._generation = generation
            self._sequence = sequence
            self._resnapshot_required = False
            self._discontinuity_reason = None
            self._condition.notify_all()

    def close(self) -> None:
        """Reject future publications and release all waiting consumers."""

        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _invalidate(self, event: RuntimeEvent, reason: str) -> None:
        self._events.clear()
        self._generation = event.generation
        self._sequence = event.sequence
        self._resnapshot_required = True
        self._discontinuity_reason = reason
        self._events.append(
            RuntimeEvent.discontinuity(
                generation=event.generation,
                sequence=event.sequence,
                occurred_at=datetime.now(timezone.utc),
                reason=reason,
            )
        )
        self._condition.notify_all()
