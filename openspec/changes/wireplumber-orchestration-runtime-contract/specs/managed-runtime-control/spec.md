## Purpose

Provide safe and predictable WirePlumber mutations for orchestration while preserving ownership boundaries and confirming changes through observed runtime state.

## ADDED Requirements

### Requirement: Serialized control execution
The binding SHALL serialize all runtime mutations onto the WirePlumber event-loop context and SHALL preserve request order per connection generation.

#### Scenario: Concurrent callers submit controls
- **WHEN** multiple application threads submit mutations concurrently
- **THEN** the binding executes them in a defined order on the WirePlumber context without concurrent native proxy access

### Requirement: Structured control outcomes
Every mutation SHALL return a structured outcome containing the request identity, generation, operation, status, and structured failure details when unsuccessful.

#### Scenario: Mutation succeeds
- **WHEN** WirePlumber accepts a valid mutation and the requested state is observed
- **THEN** the result identifies the successful request and its confirming observation

#### Scenario: Preconditions are stale
- **WHEN** a mutation references a stale generation, sequence, or object identity
- **THEN** the mutation is rejected with a precondition failure before affecting another runtime object

### Requirement: Observed-state confirmation
Successful mutation submission SHALL not by itself prove convergence; the binding SHALL correlate or await an observed event or snapshot state that confirms the requested effect, subject to a caller-supplied timeout.

#### Scenario: Requested value is confirmed
- **WHEN** the observed runtime state reaches the requested value before the deadline
- **THEN** the mutation outcome reports confirmed success

#### Scenario: Runtime does not converge
- **WHEN** submission is accepted but the requested state is not observed before the deadline
- **THEN** the outcome reports an unconfirmed or timed-out failure without inventing success

### Requirement: Typed parameter controls
The binding SHALL provide typed controls for volume, mute, channels, audio formats, and other supported SPA parameters while retaining a validated generic parameter escape hatch.

#### Scenario: Set node volume and mute
- **WHEN** an application submits valid volume and mute values for a current node
- **THEN** the binding encodes the appropriate SPA parameters and confirms the observed values

#### Scenario: Submit an invalid parameter value
- **WHEN** a parameter violates its documented type or range
- **THEN** validation fails before the native mutation is executed

### Requirement: Metadata defaults and targets
The binding SHALL support setting and clearing managed metadata values used for default nodes and explicit stream targets.

#### Scenario: Change the default audio sink
- **WHEN** an application requests a current sink as the managed default
- **THEN** the binding writes the appropriate metadata value and confirms the new observed default

#### Scenario: Clear an explicit stream target
- **WHEN** an application clears a managed target override
- **THEN** the binding removes that override without deleting unrelated metadata

### Requirement: Profile and route controls
The binding SHALL support selecting available device profiles and routes, including route properties that WirePlumber exposes as writable.

#### Scenario: Activate an available headset route
- **WHEN** an application selects an available route using current device and route identities
- **THEN** the binding applies the route and confirms it as active

#### Scenario: Select an unavailable profile
- **WHEN** an application requests a profile that is absent or unavailable in current state
- **THEN** the binding returns a validation or precondition failure without changing the active profile

### Requirement: Explicit managed-link ownership
The binding SHALL create, update, and destroy only links carrying an ownership identity explicitly assigned by the calling orchestrator.

#### Scenario: Reconcile an owned link
- **WHEN** an application requests a link with its ownership identity and that link already exists
- **THEN** the operation is idempotent and does not create a duplicate link

#### Scenario: Encounter an unmanaged link
- **WHEN** reconciliation finds a matching or conflicting link without the caller's ownership identity
- **THEN** the binding reports it but does not destroy or silently adopt it

### Requirement: Generation-safe cancellation and shutdown
Queued or pending controls SHALL be cancelled when their connection generation is lost or the runtime stops.

#### Scenario: Disconnect during a pending control
- **WHEN** continuity is lost before a mutation is executed or confirmed
- **THEN** its outcome reports cancellation due to generation loss and it is not replayed automatically on the next connection

#### Scenario: Shutdown with queued controls
- **WHEN** the binding shuts down with controls waiting
- **THEN** callers are released with structured cancellation outcomes
