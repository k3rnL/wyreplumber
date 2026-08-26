"""Minimal long-lived consumer of WyrePlumber's orchestration contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    MutationOutcome,
    MutationStatus,
    RuntimeContinuityError,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeObjectKind,
    RuntimeSnapshot,
    capture_runtime_snapshot,
    drain_runtime_events,
    next_runtime_event,
    require_event_continuity,
    require_orchestration_contract,
    set_node_volume,
)


ProjectionKey = tuple[RuntimeObjectKind, int | str]


@dataclass(slots=True)
class RuntimeProjection:
    """A small example reducer; applications can use richer domain indexes."""

    generation: int
    sequence: int
    objects: dict[ProjectionKey, object] = field(default_factory=dict)

    @classmethod
    def from_snapshot(cls, snapshot: RuntimeSnapshot) -> "RuntimeProjection":
        projection = cls(snapshot.generation, snapshot.sequence)
        collections = (
            (RuntimeObjectKind.DEVICE, snapshot.devices, lambda value: value.id),
            (RuntimeObjectKind.NODE, snapshot.nodes, lambda value: value.id),
            (RuntimeObjectKind.PORT, snapshot.ports, lambda value: value.id),
            (RuntimeObjectKind.LINK, snapshot.links, lambda value: value.id),
            (RuntimeObjectKind.METADATA, snapshot.metadata, lambda value: value.id),
            (
                RuntimeObjectKind.PARAMETER,
                snapshot.parameters,
                lambda value: f"{value.owner_type}:{value.owner_id}:{value.id}",
            ),
            (
                RuntimeObjectKind.PROFILE,
                snapshot.profiles,
                lambda value: f"{value.device_id}:{value.index}",
            ),
            (
                RuntimeObjectKind.ROUTE,
                snapshot.routes,
                lambda value: f"{value.device_id}:{value.index}",
            ),
        )
        for kind, values, identity in collections:
            for value in values:
                projection.objects[(kind, identity(value))] = value
        projection.objects[(RuntimeObjectKind.DEFAULTS, "defaults")] = snapshot.defaults
        projection.objects[(RuntimeObjectKind.CONNECTION, "connection")] = snapshot.health
        return projection

    def apply(self, event: RuntimeEvent) -> None:
        require_event_continuity(
            event,
            generation=self.generation,
            sequence=self.sequence,
        )
        key = (event.object_kind, event.object_id)
        if event.kind is RuntimeEventKind.OBJECT_REMOVED:
            self.objects.pop(key, None)
        elif event.current is not None:
            self.objects[key] = event.current
        self.sequence = event.sequence


class RuntimeClient:
    """Bootstrap a snapshot, project events, and recover lost continuity."""

    def __init__(self, connection: WPConnection) -> None:
        require_orchestration_contract(1, 1)
        self.connection = connection
        self.snapshot: RuntimeSnapshot
        self.projection: RuntimeProjection
        self.resnapshot()

    def resnapshot(self) -> None:
        """Replace local state and fold in events racing with the capture."""

        while True:
            snapshot = capture_runtime_snapshot(self.connection)
            projection = RuntimeProjection.from_snapshot(snapshot)
            try:
                for event in drain_runtime_events(self.connection):
                    if (
                        event.generation == projection.generation
                        and event.sequence <= projection.sequence
                    ):
                        continue
                    projection.apply(event)
            except RuntimeContinuityError:
                continue
            self.snapshot = snapshot
            self.projection = projection
            return

    def project_next_event(self, timeout: float | None = None) -> bool:
        event = next_runtime_event(self.connection, timeout=timeout)
        if event is None:
            return False
        try:
            self.projection.apply(event)
        except RuntimeContinuityError:
            self.resnapshot()
        return True

    def set_volume(self, node_id: int, volume: float) -> MutationOutcome:
        """Issue one confirmed control against the projected continuity point."""

        outcome = set_node_volume(
            self.connection,
            node_id=node_id,
            volume=volume,
            expected_generation=self.projection.generation,
            expected_sequence=self.projection.sequence,
        )
        # Confirmation captures newer state internally, so replace the projection
        # before issuing another sequence-guarded control.
        self.resnapshot()
        return outcome


def main() -> None:
    connection = WPConnection()
    try:
        client = RuntimeClient(connection)
        sink = next(
            node
            for node in client.snapshot.nodes
            if node.media_class == "Audio/Sink"
        )
        outcome = client.set_volume(sink.id, 0.5)
        if outcome.status is not MutationStatus.CONFIRMED:
            raise RuntimeError(f"volume was not confirmed: {outcome.failure}")
        while client.project_next_event(timeout=30):
            pass
    finally:
        connection.stop()


if __name__ == "__main__":
    main()
