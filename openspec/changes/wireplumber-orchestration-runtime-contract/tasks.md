## 1. Detached Observation Values

- [x] 1.1 Define frozen detached Python value objects for devices, nodes, ports, links, metadata, parameters, profiles, routes, defaults, and connection health; add JSON serialization round-trip and immutability tests.
- [x] 1.2 Define a coherent runtime snapshot with generation, sequence, capture time, typed collections, indexes, and unresolved-relationship reporting; add validation tests.
- [x] 1.3 Normalize the SPA values needed for volume, mute, channels, audio formats, profiles, and routes while preserving unknown JSON-compatible fields; add representative fixtures and tests.
- [x] 1.4 Publish orchestration contract version 1 and document the detached public API, serialization guarantees, identity scope, and compatibility policy.

## 2. Snapshot and Event Runtime

- [x] 2.1 Add a native bulk extraction boundary that copies primitive registry, property, metadata, parameter, profile, route, default, and health data only on the WirePlumber context.
- [x] 2.2 Build and validate immutable snapshots from bulk extraction payloads without retaining native proxies; add lifecycle and disappearing-object tests.
- [x] 2.3 Define detached ordered event values for object, parameter, metadata, default, health, discontinuity, and resnapshot transitions.
- [x] 2.4 Implement the bounded thread-safe event queue with blocking/non-blocking reads, ordered delivery, explicit overflow, closure, and resnapshot semantics.
- [x] 2.5 Wire native registry and connection signals into bounded detached event publication without invoking application callbacks on the WirePlumber thread.
- [x] 2.6 Implement reconnect generation changes, monotonic per-generation sequences, waiter release, and deterministic shutdown; test disconnect, reconnect, overflow, and stop behavior.
- [x] 2.7 Port the native build boundary and container integration environment to the selected WirePlumber 0.5 family while preserving the documented legacy proxy migration surface.

## 3. Managed Runtime Controls

- [x] 3.1 Define mutation requests, expected-generation/sequence preconditions, structured outcomes and failures, deadlines, cancellation, and confirmation predicates.
- [x] 3.2 Implement a connection-owned dispatcher that serializes mutations on the WirePlumber context and cancels stale-generation or shutdown work.
- [x] 3.3 Implement typed and generic parameter controls, including volume and mute, with validation, idempotency, and observed-state confirmation tests.
- [x] 3.4 Implement managed metadata controls for defaults and explicit stream targets, including safe clear behavior and confirmation tests.
- [x] 3.5 Implement available profile and route selection, writable route properties, stale-identity checks, and observed-state confirmation tests.
- [x] 3.6 Implement explicitly owned link creation, idempotent reconciliation, conflict reporting, and removal that never adopts or destroys unmanaged links.

## 4. Integration and Release Readiness

- [x] 4.1 Add WirePlumber 0.5 integration scenarios for coherent snapshots, event ordering, overflow recovery, reconnection, parameters, metadata, profiles/routes, and managed links.
- [x] 4.2 Add package API/type-stub coverage and consumer examples for snapshot bootstrap, event projection, resnapshot recovery, and confirmed controls.
- [x] 4.3 Run the pure and container-backed test suites, build distributions, verify contract metadata, and record the tested WirePlumber/PipeWire/Python compatibility matrix for the Open Cinema pin.
