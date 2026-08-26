## Purpose

Provide applications with a coherent, immutable, and serializable view of WirePlumber runtime state without exposing native object lifetimes or callback-thread hazards.

## ADDED Requirements

### Requirement: Detached immutable runtime values
The binding SHALL represent observed devices, nodes, ports, links, metadata, parameters, profiles, routes, defaults, and connection health as immutable Python values containing no live native proxy.

#### Scenario: Value outlives its native object
- **WHEN** an application retains an observed value after the corresponding native object disappears
- **THEN** every field on the retained value remains readable without accessing released native state

#### Scenario: Value cannot be mutated
- **WHEN** application code attempts to replace a field or mutate nested properties on an observed value
- **THEN** the operation fails without changing that value

### Requirement: Stable serialization contract
Every detached runtime value SHALL round-trip through a JSON-compatible representation that carries an explicit value type and schema version.

#### Scenario: Serialize and restore a value
- **WHEN** a supported runtime value is serialized and restored
- **THEN** the restored value has the same concrete type and compares equal to the original value

#### Scenario: Reject an unsupported schema
- **WHEN** an application restores a representation with an unsupported schema version or value type
- **THEN** the binding returns a structured validation failure rather than silently discarding fields

### Requirement: Coherent runtime snapshots
The binding SHALL capture a complete runtime snapshot containing one connection generation, one monotonic sequence, a capture time, connection health, all supported values, and validated relationships between them.

#### Scenario: Capture a connected graph
- **WHEN** an application requests a snapshot from a connected runtime
- **THEN** all included objects and relationships describe one coherent capture generation and sequence

#### Scenario: Relationship target is absent
- **WHEN** a captured link, route, profile, default, or parent reference points to an object absent from the same snapshot
- **THEN** the snapshot identifies the relationship as unresolved instead of fabricating a target

### Requirement: Ordered detached runtime events
The binding SHALL publish detached events with a connection generation, monotonic sequence, event kind, object kind, stable object identity, and enough state to update or invalidate an application projection.

#### Scenario: Consume consecutive events
- **WHEN** an application receives consecutive events within one connection generation
- **THEN** event sequences are strictly increasing and their payloads contain no live native proxy

#### Scenario: Detect discontinuity
- **WHEN** an event sequence is missing, the queue overflows, or the connection generation changes
- **THEN** the binding explicitly requires the application to obtain a new snapshot

### Requirement: Bounded thread-safe event delivery
Native callbacks SHALL detach bounded data and enqueue notifications without invoking application code, and applications SHALL consume those notifications through a bounded thread-safe queue.

#### Scenario: Slow consumer reaches queue capacity
- **WHEN** producers exceed the configured queue capacity before an application drains it
- **THEN** the queue exposes an overflow condition and requires a resnapshot without blocking the WirePlumber event loop indefinitely

#### Scenario: Concurrent queue consumption
- **WHEN** an application waits for events while the WirePlumber thread publishes them
- **THEN** delivery remains ordered and safe across the thread boundary

### Requirement: Explicit connection lifecycle
Connection health SHALL distinguish connecting, connected, degraded, reconnecting, disconnected, and stopped states and SHALL assign a new generation after continuity is lost.

#### Scenario: Runtime reconnects
- **WHEN** the WirePlumber connection is re-established after a disconnect
- **THEN** connection health reports a new generation and consumers must replace state from a fresh snapshot

#### Scenario: Binding shuts down
- **WHEN** an application stops the runtime connection
- **THEN** pending waiters are released, health becomes stopped, and no subsequent native callback invokes application code

### Requirement: Typed SPA observation
The binding SHALL normalize SPA values required for volume, mute, channel topology, audio formats, profiles, and routes into documented JSON-compatible representations while preserving unknown fields.

#### Scenario: Observe a known audio parameter
- **WHEN** WirePlumber exposes a supported audio parameter
- **THEN** the detached representation provides its documented typed fields and preserves its original parameter identity

#### Scenario: Observe an unknown SPA field
- **WHEN** a supported parameter contains an unrecognized field
- **THEN** the detached representation retains that field in its JSON-compatible payload instead of dropping the entire parameter

### Requirement: Versioned orchestration boundary
The binding SHALL publish an orchestration contract version and SHALL support the selected WirePlumber 0.5 API family for contract version 1.

#### Scenario: Consumer checks compatibility
- **WHEN** an application reads the binding's orchestration contract version
- **THEN** it can reject an incompatible contract before starting continuous orchestration

#### Scenario: Existing proxy consumer migrates incrementally
- **WHEN** a consumer still uses the existing live proxy API during the migration period
- **THEN** the detached observation API can coexist without changing the proxy API's documented behavior
