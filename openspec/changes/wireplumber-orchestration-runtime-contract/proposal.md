## Why

Open Cinema needs a long-lived, safe view of WirePlumber state, but WyrePlumber currently exposes live native wrapper objects and synchronous object lists without a coherent snapshot or event continuity contract. The binding must detach application-facing data from GObject lifetimes before it can safely drive continuous orchestration.

## What Changes

- Add immutable, serializable Python value objects for all runtime observations.
- Add coherent snapshots with connection generations, monotonic sequences, capture times, and validated relationships.
- Add ordered detached events through a bounded thread-safe queue with overflow and resnapshot semantics.
- Normalize typed SPA parameters needed for volume, mute, formats, channels, profiles, and routes.
- Add serialized runtime controls for parameters, metadata, defaults, targets, profiles/routes, and explicitly managed links.
- Publish an explicit orchestration contract version and WirePlumber 0.5 compatibility boundary.
- Preserve the current proxy API during migration while ensuring snapshots and events never expose native object lifetimes.

## Capabilities

### New Capabilities

- `detached-runtime-observation`: Immutable value objects, coherent snapshots, connection lifecycle, and ordered event delivery.
- `managed-runtime-control`: Typed, serialized, confirmed WirePlumber mutations with ownership and structured failures.

### Modified Capabilities

None. This repository has no existing OpenSpec capability specifications.

## Impact

- Adds public Python modules for runtime models, snapshots, events, queues, and controls.
- Extends the native connection boundary to extract data and enqueue bounded notifications safely.
- Changes the build target from the WirePlumber 0.4 development API to the selected 0.5 family.
- Adds pure unit tests plus PipeWire/WirePlumber container integration tests.
- Open Cinema will consume contract version 1 and pin a tested WyrePlumber revision during coordinated development.
