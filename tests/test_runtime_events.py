import json

import pytest

from wyreplumber.runtime import (
    ConnectionHealthValue,
    ConnectionState,
    DefaultsValue,
    DeviceValue,
    LinkValue,
    MetadataValue,
    NodeValue,
    ParameterValue,
    PortDirection,
    PortValue,
    RuntimeContinuityError,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeObjectKind,
    require_event_continuity,
    runtime_value_from_dict,
)


EVENTS = (
    RuntimeEvent(
        generation=3,
        sequence=6,
        occurred_at="2026-08-22T12:31:00Z",
        kind=RuntimeEventKind.OBJECT_ADDED,
        object_kind=RuntimeObjectKind.DEVICE,
        object_id=10,
        current=DeviceValue(id=10, name="usb-headset"),
    ),
    RuntimeEvent(
        generation=3,
        sequence=7,
        occurred_at="2026-08-22T12:31:01Z",
        kind=RuntimeEventKind.OBJECT_ADDED,
        object_kind=RuntimeObjectKind.NODE,
        object_id=20,
        current=NodeValue(id=20, name="main-speakers"),
    ),
    RuntimeEvent(
        generation=3,
        sequence=8,
        occurred_at="2026-08-22T12:31:02Z",
        kind=RuntimeEventKind.OBJECT_CHANGED,
        object_kind=RuntimeObjectKind.PORT,
        object_id=30,
        previous=PortValue(id=30, node_id=20, direction=PortDirection.INPUT),
        current=PortValue(
            id=30,
            node_id=20,
            direction=PortDirection.INPUT,
            channel="FL",
        ),
    ),
    RuntimeEvent(
        generation=3,
        sequence=9,
        occurred_at="2026-08-22T12:31:03Z",
        kind=RuntimeEventKind.OBJECT_REMOVED,
        object_kind=RuntimeObjectKind.LINK,
        object_id=40,
        previous=LinkValue(
            id=40,
            output_node_id=21,
            output_port_id=32,
            input_node_id=20,
            input_port_id=30,
        ),
    ),
    RuntimeEvent(
        generation=3,
        sequence=10,
        occurred_at="2026-08-22T12:31:04Z",
        kind=RuntimeEventKind.PARAMETER_CHANGED,
        object_kind=RuntimeObjectKind.PARAMETER,
        object_id="node:20:Props",
        current=ParameterValue(
            owner_type="node",
            owner_id=20,
            id="Props",
            permissions="rw",
            values=({"mute": True},),
        ),
    ),
    RuntimeEvent(
        generation=3,
        sequence=11,
        occurred_at="2026-08-22T12:31:05Z",
        kind=RuntimeEventKind.METADATA_CHANGED,
        object_kind=RuntimeObjectKind.METADATA,
        object_id=50,
        current=MetadataValue(id=50, name="default"),
    ),
    RuntimeEvent(
        generation=3,
        sequence=12,
        occurred_at="2026-08-22T12:31:06Z",
        kind=RuntimeEventKind.DEFAULT_CHANGED,
        object_kind=RuntimeObjectKind.DEFAULTS,
        object_id="defaults",
        current=DefaultsValue(metadata_id=50),
    ),
    RuntimeEvent(
        generation=3,
        sequence=13,
        occurred_at="2026-08-22T12:31:07Z",
        kind=RuntimeEventKind.CONNECTION_CHANGED,
        object_kind=RuntimeObjectKind.CONNECTION,
        object_id="connection",
        current=ConnectionHealthValue(
            state=ConnectionState.DEGRADED,
            generation=3,
            reason="event extraction delayed",
        ),
    ),
    RuntimeEvent.discontinuity(
        generation=3,
        sequence=14,
        occurred_at="2026-08-22T12:31:08Z",
        reason="native event sequence was lost",
    ),
)


@pytest.mark.parametrize("event", EVENTS, ids=lambda event: event.kind.value)
def test_detached_events_round_trip_through_json(event):
    encoded = json.loads(json.dumps(event.to_dict(), allow_nan=False))

    restored = runtime_value_from_dict(encoded)

    assert type(restored) is RuntimeEvent
    assert restored == event


def test_event_current_and_previous_values_are_immutable():
    event = EVENTS[2]

    with pytest.raises(AttributeError):
        event.current.channel = "FR"


def test_event_continuity_accepts_the_immediate_next_event():
    event = EVENTS[0]

    assert require_event_continuity(event, generation=3, sequence=5) is event


@pytest.mark.parametrize(
    ("event", "generation", "sequence", "code"),
    (
        (EVENTS[0], 2, 5, "generation_changed"),
        (EVENTS[1], 3, 5, "sequence_gap"),
        (EVENTS[-1], 3, 13, "resnapshot_required"),
    ),
)
def test_event_continuity_classifies_invalid_projection_updates(
    event,
    generation,
    sequence,
    code,
):
    with pytest.raises(RuntimeContinuityError) as error:
        require_event_continuity(event, generation=generation, sequence=sequence)

    assert error.value.code == code
    assert error.value.event is event


def test_discontinuity_requires_a_reason_and_resnapshot():
    event = RuntimeEvent.discontinuity(
        generation=3,
        sequence=6,
        occurred_at="2026-08-22T12:31:00Z",
        reason="queue overflow",
    )

    assert event.requires_resnapshot
    assert event.object_kind is RuntimeObjectKind.RUNTIME
    assert event.reason == "queue overflow"

    with pytest.raises(ValueError, match="must require"):
        RuntimeEvent(
            generation=3,
            sequence=6,
            occurred_at="2026-08-22T12:31:00Z",
            kind=RuntimeEventKind.DISCONTINUITY,
            object_kind=RuntimeObjectKind.RUNTIME,
            object_id="runtime",
        )
