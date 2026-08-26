## Context

See `proposal.md` for motivation. The existing extension presents native WirePlumber proxies directly to Python and services calls through a background GLib main loop. Those proxy lifetimes and callback threading rules are unsuitable as a durable application model. Open Cinema instead needs a stable projection it can snapshot, incrementally update, discard on continuity loss, and reconcile through explicit controls.

The first production boundary targets the WirePlumber 0.5 family. The present 0.4 proxy API and experimental SPA work must remain usable during migration, so the new API is additive until consumers have moved.

## Goals / Non-Goals

**Goals:**

- Make all application-facing observations immutable, detached from GObjects, JSON-compatible, and explicitly versioned.
- Establish one coherent state stream made of an initial snapshot plus ordered events within a connection generation.
- Keep native callbacks short and prevent application code from running on the WirePlumber thread.
- Serialize controls on the native event-loop context and confirm them from observation.
- Define ownership rules that prevent the binding from removing links or metadata belonging to other policy components.

**Non-Goals:**

- Implement Open Cinema routing policy, desired graph selection, fallbacks, or UI concepts in this repository.
- Replace WirePlumber's own policy engine or expose every SPA type in contract version 1.
- Guarantee continuity across a WirePlumber restart or reconnect; those transitions deliberately require a fresh snapshot.
- Remove the current proxy API in this change.

## Decisions

### Detached Python value layer

Public observation types will be frozen, slotted dataclasses. Nested mappings and sequences will be recursively frozen into immutable value containers, with explicit conversion to and from JSON-compatible dictionaries. Each serialized value carries `schema_version` and `value_type`; a central decoder rejects unknown types or schema versions.

This is preferable to returning native wrappers because a value remains valid after its proxy disappears. It is preferable to loose dictionaries because constructors, equality, type hints, and validation form a stable public contract. `MappingProxyType` was considered but rejected because it does not provide a convenient recursive or serialization contract.

Types will cover devices, nodes, ports, links, metadata entries/sets, parameters, profiles, routes, defaults, and connection health. Stable WirePlumber identifiers are preserved as integers where available, while optional semantic names and relationship identifiers remain explicit fields.

### Native extraction, Python construction

Native code may inspect GObjects only on the GLib/WirePlumber context. It will copy bounded primitive data before leaving that context. Python then constructs public values from copied payloads; snapshots and events never contain extension proxy instances.

A bulk capture operation will enumerate objects and their properties in one serialized main-loop task. It assigns a generation and sequence after the registry sync boundary and validates relationships while building the immutable snapshot. Separate calls to existing `get_nodes()` and similar methods are not composed into a snapshot because objects could change between calls.

### Generation and sequence continuity

One connection generation begins when a synchronized connection becomes usable. Every snapshot and event includes that generation. Event sequences increase monotonically within it. Disconnect, event overflow, extraction failure that loses ordering, or shutdown ends continuity. Reconnection starts a new generation and requires a fresh snapshot.

This explicit reset is simpler and safer than attempting to merge identities across WirePlumber restarts, where object identifiers can be reused.

### Bounded event queue

Native signal handlers will copy the minimum event payload and publish it to a Python-owned bounded queue without invoking consumer callbacks. The queue uses a lock/condition and preserves order for single and multiple consumers. At capacity it records one overflow discontinuity, stops pretending its incremental contents are complete, and wakes consumers to request a new snapshot.

An unbounded queue was rejected because a stalled web service could grow memory indefinitely. Calling Python application callbacks from native signals was rejected because it risks deadlocks, re-entrancy, and long stalls on the WirePlumber thread.

### SPA normalization

Contract version 1 will define JSON-compatible shapes for the parameters Open Cinema needs first: volume, mute, channels, formats, profiles, and routes. Known SPA fields receive typed names and validation. Unknown fields inside a supported parameter are retained in an `extra` payload after recursive normalization so the contract can evolve without losing diagnostic information.

The current experimental SPA value classes can remain an internal or advanced API, but snapshot/event values use the normalized contract and do not embed mutable or native objects.

### Serialized controls and confirmation

Every mutation is represented as a request with a unique request identity, expected generation, optional expected sequence, operation, target, payload, and deadline. A connection-owned dispatcher serializes requests onto the GLib context. It validates generation and target identity immediately before native execution.

Submission acceptance is distinct from success. A pending request is completed only when an observation confirms its predicate, or it fails, times out, disconnects, or is cancelled during shutdown. Idempotent requests whose predicate is already true return confirmed success without another write.

Controls will offer typed helpers for common parameters, metadata defaults/targets, device profiles/routes, and managed links, backed by a validated generic parameter operation for advanced consumers.

### Managed ownership

Created links and managed metadata include a caller-provided ownership namespace and stable desired identity. Reconciliation may mutate or remove only objects with that ownership. Unmanaged objects are observable and may cause structured conflicts, but are never silently adopted or destroyed.

Ownership is explicit rather than inferred from topology because another WirePlumber policy, desktop application, or administrator may create an identical-looking link for a different reason.

### Public compatibility boundary

The package publishes orchestration contract version `1`. The build and integration suite target WirePlumber 0.5, while the legacy proxy surface stays additive during migration. Open Cinema checks the contract version at startup and pins a tested WyrePlumber revision for deployment; a local path dependency is acceptable only in development.

## Risks / Trade-offs

- **[Snapshot extraction briefly occupies the WirePlumber context]** → Keep extraction bounded, avoid arbitrary Python callbacks, measure representative large registries, and add latency tests.
- **[Queue overflow discards incremental continuity]** → Make overflow explicit and recovery deterministic through a fresh snapshot rather than attempting an unsafe partial merge.
- **[WirePlumber object identifiers are not permanent]** → Scope every identity and mutation to a connection generation.
- **[Observed confirmation can be delayed by policy components]** → Use explicit deadlines and distinguish rejected, timed-out, cancelled, and confirmed outcomes.
- **[The 0.5 port can disturb the 0.4 prototype API]** → Keep the detached API additive, test both pure value behavior and container-backed runtime behavior, and migrate native calls in small steps.
- **[Recursive JSON normalization can lose exotic SPA semantics]** → Preserve unknown fields and original parameter identity, and extend typed shapes under a future contract version when semantics change incompatibly.

## Migration Plan

1. Add pure immutable value types and round-trip tests without changing native behavior.
2. Add the bulk snapshot extractor and relationship validation behind the new API.
3. Add normalized SPA values, ordered events, the bounded queue, and lifecycle handling.
4. Port the native build and runtime integration suite to WirePlumber 0.5 and publish contract version 1.
5. Add serialized, confirmed controls, beginning with volume/mute and then metadata, profiles/routes, and managed links.
6. Integrate Open Cinema against a local path dependency during development, then pin a tested revision for CI and deployment.
7. Retire the legacy proxy API only in a separately specified breaking release after all consumers migrate.

Rollback consists of disabling the consuming Open Cinema feature flag and returning to the last pinned binding revision. The additive proxy API remains available during this change.
