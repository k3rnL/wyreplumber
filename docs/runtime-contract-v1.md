# WyrePlumber orchestration contract v1

Contract version 1 is the additive API boundary intended for long-lived audio orchestration consumers such as Open Cinema. It coexists with the original live proxy API while consumers migrate.

## Compatibility check

Consumers must check the contract before starting runtime observation or mutation:

```python
from wyreplumber import require_orchestration_contract

contract = require_orchestration_contract(minimum=1, maximum=1)
```

The check raises `OrchestrationContractCompatibilityError` when the installed version is outside the accepted range. `ORCHESTRATION_CONTRACT` is also available as machine-readable metadata. Contract v1 targets the WirePlumber 0.5 API family and Python 3.12 or later.

The v1 implementation is currently marked `development`. Normal builds and all
CI/release builds require `wireplumber-0.5`; a missing 0.5 development package
is an error rather than a reason to produce a different binary. The preserved
legacy proxy migration surface can still be compiled explicitly with
`WYREPLUMBER_WP_API=0.4` for migration investigation, but those binaries are
not supported orchestration-v1 deployment artifacts.

`wyreplumber.WIREPLUMBER_BUILD_API_FAMILY` reports the family used to compile the installed native extension. Production consumers should require both orchestration contract `1` and native build family `"0.5"`; the latter is distinct from the runtime library version reported in snapshot health details.

## Tested compatibility and Open Cinema pin

The following combinations were exercised on 2026-08-22. “Full suite” means
all 195 pure and live PipeWire tests, including snapshot coherence, ordered
events, queue overflow, reconnect, parameters, metadata, profiles/routes, and
managed-link ownership.

| Purpose | Python | WirePlumber build API | PipeWire | Platform | Evidence |
| --- | --- | --- | --- | --- | --- |
| Open Cinema contract baseline | 3.12.14 | 0.5.8 (`wireplumber-0.5`) | 1.4.2 client and server | Linux x86_64 | Full suite passed; wheel and source distribution passed Twine validation; installed wheel reported contract 1 and build family 0.5 |
| Historical legacy proxy migration regression (not a release target) | 3.12.3 | 0.4.17 (`wireplumber-0.4`) | 1.0.5 client, 1.4.2 test server | Linux x86_64 | Preserved only as migration evidence |

The production Open Cinema dependency must be built against the first row and
must check both `require_orchestration_contract(1, 1)` and
`WIREPLUMBER_BUILD_API_FAMILY == "0.5"` at startup. During coordinated
development, Open Cinema may use an editable local path to this repository.
Deployment must instead pin the exact WyrePlumber commit containing this change;
the pre-change base revision (`e58456fd9b1f94b778b39f5529ba10d16bdc68c3`)
is not a valid production pin because the implementation currently remains in
the development working tree.

Python 3.13/3.14 and Linux aarch64 are present in the release CI matrix, but
they are not promoted into this tested contract matrix until that CI run is
green. Raspberry Pi hardware behavior, real ALSA profile/route selection, and
CamillaDSP integration likewise remain consumer-level verification work rather
than claims of this binding release.

## Detached values

All durable observation types live under `wyreplumber.runtime`. Their names end in `Value`, except for the aggregate `RuntimeSnapshot`. They are frozen values and never contain a `WPNode`, `WPPort`, `WPMetadata`, `WpPipewireObject`, GObject, native pointer, or callable application callback.

Mappings are recursively converted to `FrozenDict` and sequences to tuples. Retaining a value never retains the corresponding native object. Applications may therefore keep values after an object disappears, compare them, serialize them, and move them between threads.

SPA values used by orchestration are normalized with `normalize_spa_parameter()`. Known volume, mute, channel, format, profile, and route fields receive typed values. Unknown JSON-compatible SPA fields remain in an immutable `extra` or `properties` mapping. Binary unknown values use an explicit base64 representation.

## Serialization

`RuntimeValue.to_dict()` returns a detached JSON-compatible dictionary. Every envelope has:

- `schema_version`, currently `1`;
- `value_type`, identifying the concrete value;
- all serialized fields of that value.

`runtime_value_from_dict()` restores any known value, while `<Type>.from_dict()` also verifies the expected concrete type. Unknown schema versions, value types, and fields are rejected with `RuntimeValueDecodeError`; fields are never silently discarded. Non-finite numbers and unsupported Python/native objects are rejected.

Indexes on `RuntimeSnapshot` are immutable derived views and are deliberately omitted from serialization. They are rebuilt and relationship validation is repeated when a snapshot is restored. A serialized unresolved-relationship list that does not match the restored contents is rejected.

## Identity and consistency

PipeWire global IDs and compound parameter/profile/route keys are stable only inside one connection generation. They must never be persisted as permanent hardware identity or reused to control an object after generation loss.

A snapshot contains one generation, monotonic sequence, UTC capture time, and a `ConnectionHealthValue` with the same generation. Relationships resolve only against objects in that snapshot. Missing or inconsistent targets appear as `UnresolvedRelationshipValue`; they are not replaced with stale objects from an earlier snapshot.

Hardware and logical identity belong to the consuming orchestration layer. Consumers should match stable properties such as declared Open Cinema IDs, device serials, names, media classes, or configured selectors and then bind the resulting runtime ID only for the current generation.

## Lifetime and threading

The original `_core` proxy objects remain subject to native lifetime and WirePlumber-thread rules. They are migration and low-level APIs, not durable state.

Detached values are safe to read from any Python thread. Native extraction occurs as one bounded operation on the WirePlumber/GLib context and copies primitive payloads before returning to application code. Native signals do not execute consumer callbacks. Ordered events use the bounded connection queue, and managed controls use the serialized connection dispatcher.

Within one connection generation, a snapshot sequence establishes the projection baseline and subsequent event sequences must increase monotonically. Events may be applied only to a projection with the same generation and an immediately preceding sequence. A missing sequence, queue overflow, extraction failure that loses ordering, or explicit discontinuity invalidates the projection; consumers must discard it and request a new coherent snapshot instead of guessing the missing state.

A disconnect ends the current generation. Reconnection creates a new generation and always requires a complete snapshot, even when runtime IDs appear unchanged. Shutdown releases pending waiters, cancels generation-scoped work, and publishes no later application callback. These reset rules deliberately favor deterministic recovery over attempting to merge state across a PipeWire or WirePlumber restart.

## Managed mutation values

Managed controls use detached `MutationRequest` and `MutationOutcome` envelopes. Defining these values does not permit a caller to bypass the connection dispatcher: native execution and confirmation remain serialized on the WirePlumber context.

A request contains a caller-visible unique ID, expected generation, optional expected sequence, operation, generation-scoped target, immutable payload, request time, absolute UTC deadline, and one or more declarative `ConfirmationPredicateValue` instances. Predicates address detached observation fields by a path of mapping keys and sequence indexes and support equality, presence, or absence. Python callables and native objects are deliberately not valid predicates or payload values.

The expected generation and sequence are preconditions, not hints. A dispatcher must reject a stale request before native execution and must not replay it in a later generation. `MutationRequest.create()` converts a relative timeout into the serialized absolute deadline; a zero timeout represents an immediately expired request.

Every terminal outcome identifies the request, generation, operation, status, and completion time. Confirmed outcomes contain the exact detached observations and sequences that satisfied their predicates. All other outcomes contain a structured `MutationFailureValue` with a phase, stable code, message, retryability flag, and immutable diagnostic details. Rejection, native failure, confirmation timeout, deadline expiry, generation loss, runtime shutdown, and caller cancellation remain distinct; acceptance by WirePlumber alone is never represented as confirmed success.

`dispatch_runtime_mutation()` enters a connection-owned FIFO and returns a `MutationDispatchTicketValue` after the serialized native handler runs on the WirePlumber context. A ready ticket means the handler accepted the submission after generation and optional sequence preconditions held; it is still not a confirmed mutation outcome. Stale preconditions are rejected without entering a later generation. Reconnect and shutdown cancel requests that remain queued, release their callers, and never replay them. Dispatch order starts again at one for each synchronized generation.

### Parameter controls

`set_runtime_parameter()` is the validated escape hatch for writable device, node, and port SPA parameters. It accepts a typed SPA value, raw pod bytes, or a raw pod dictionary; validates the target, parameter identity, flags, pod envelope, deadline, and predicates before native execution; and then waits for all caller-supplied predicates to match coherent detached snapshots. Native acceptance without the requested observation ends in a confirmation timeout rather than a false success.

`set_node_audio_properties()` provides the typed `SPA_PARAM_Props` layer, with `set_node_volume()` and `set_node_mute()` as focused helpers. Volume and channel volumes must be finite non-negative numbers, mute must be a boolean, and a channel-volume list must not be empty. The typed layer normalizes floating-point expectations to the SPA float representation before confirmation.

Every parameter control captures a preflight snapshot. If all predicates already match, it returns confirmed success without dispatching another native write. Otherwise it submits exactly one generation-scoped mutation and polls coherent snapshots until every predicate is confirmed, the deadline expires, the generation changes, or the runtime stops. An optional expected sequence is checked against the preflight boundary and again by the native dispatcher. Some PipeWire node implementations apply audio properties only while their processing graph is active; the confirmation contract deliberately reports a timeout when an accepted write produces no observable state change.

### Metadata, default, and stream-target controls

`set_runtime_metadata()` and `clear_runtime_metadata()` operate on one generation-scoped metadata object, subject, and key. Both use the same preflight, FIFO dispatch, idempotency, deadline, and observed-confirmation path as parameter controls. A set confirms the detached `MetadataEntryValue` by default. A clear is implemented as `wp_metadata_set(metadata, subject, key, NULL, NULL)` and confirms that exact entry is absent; it never calls the whole-object metadata clear operation, so sibling subjects and keys remain untouched.

`set_default_node()` implements WirePlumber's configured-default convention. It accepts a current `Audio/Sink`, `Audio/Source`, or `Video/Source` node and writes subject `0`, key `default.configured.<media type>`, type `Spa:String:JSON`, and a JSON object containing the current `node.name`. Success requires both the configured metadata entry and the corresponding `DefaultsValue.resolved_node_id` to identify the requested node. This distinguishes a stored preference from policy convergence: if WirePlumber accepts the preference but does not select that node before the deadline, the outcome is a confirmation timeout. `clear_default_node()` removes only the configured key for the requested media class and leaves actual defaults and other configured preferences for WirePlumber policy to resolve.

`set_stream_target()` writes `target.object` on the default metadata object using the current stream node ID as subject. It prefers the target node's `object.serial` encoded as `Spa:Id`, matching WirePlumber 0.5's stream-state behavior, and falls back to a current `node.name` string when no serial is exposed. `clear_stream_target()` unsets only that stream's `target.object` entry. The legacy `target.node` key is deliberately not written, and unrelated per-stream ownership or policy metadata is preserved.

### Device profile and route controls

`select_device_profile()` accepts a detached `ProfileValue` from the caller's current projection. Immediately before execution it verifies that the device and profile index still exist, that the index still has the same semantic name, and that WirePlumber does not report the profile unavailable. It writes a `Spa:Pod:Object:Param:Profile` containing the selected index to the device's writable `Profile` parameter and confirms that the same profile identity is observed as active. A reused index is reported as `target_identity_changed`; a currently unavailable selection is reported as `target_unavailable`; neither reaches native execution.

`select_device_route()` applies the same current-identity and availability checks to a detached `RouteValue`, including its direction and SPA device identity. When profile compatibility information is available, a route that does not belong to the active profile is rejected before execution. The helper writes a `Spa:Pod:Object:Param:Route` containing the route index, SPA device index, save flag, and any requested writable `Spa:Pod:Object:Param:Props`. Typed route properties currently include volume, mute, and channel volumes with the same finite/non-negative validation as node controls. Confirmation requires one coherent snapshot in which the same route identity is active and every requested route property has the observed SPA value.

An already active profile or route whose requested properties match is confirmed without another write, even if its availability subsequently changed. Missing or read-only device parameters still receive the common structured `target_not_found` or `not_writable` native result. Profile and route IDs remain scoped to the request's connection generation and are never treated as permanent hardware identity.

### Explicitly managed links

`create_managed_link()` requires a caller ownership namespace, a stable desired-link identity within that namespace, and four current node/port IDs. Preflight verifies the endpoint relationships and directions. If the same managed identity already describes the same endpoints, the request is idempotently confirmed. If that identity describes different endpoints, or the exact topology already exists as an unmanaged or differently owned link, the result is `ownership_conflict`; the binding never adopts the existing link.

Native execution repeats the topology and identity conflict check immediately before using PipeWire's `link-factory`. It retains the creator proxy and a generation-scoped ownership ledger for the lifetime of the connection, and projects the owner and desired identity into detached `LinkValue` observations. This ledger is necessary because PipeWire versions differ in which caller-defined link properties they expose through registry information. Ownership is never inferred from topology alone, is discarded on generation loss, and is not reconstructed from links found after reconnect. The dispatcher controls endpoint properties and ownership markers; callers may add other string properties and may request a passive link, but cannot enable `object.linger` and leave an untracked server object behind.

`remove_managed_link()` addresses a link by owner and desired identity. An absent identity is idempotently confirmed without native execution. A duplicate identity is a conflict and removes nothing. Immediately before destruction, native execution checks that the current link ID still corresponds to the connection-owned endpoint record; a wrong owner, reused ID, or unmanaged link returns `ownership_conflict`. Removal uses PipeWire's destroy request only after that check, and confirmation requires the owned identity to be absent. Unrelated links are never removed as a side effect.

### Routing mechanism boundary

Open Cinema should select the least invasive mechanism that expresses its
intent:

| Desired shape | Mechanism | Ownership consequence |
| --- | --- | --- |
| Primary output for ordinary, unpinned playback streams | Configured default metadata | WirePlumber selects and owns session links |
| Move one movable playback stream to one output | Per-stream `target.object` metadata | WirePlumber replaces the session link; Open Cinema owns only its metadata choice |
| Controlled fan-out to several outputs | Explicit managed links, plus a planned fan-out/adapter node when required | Open Cinema owns only the labeled links it creates |
| Several sources mixed into one path | A managed mixer processor and its explicitly planned internal links | Mixing is never inferred from coincident links |
| Stable processor internals that session target/default policy cannot represent | Explicit managed links | Every removable link carries the caller owner and desired identity |

The integration suite creates two sinks and an ordinary `pw-cat` playback
stream under a real WirePlumber policy process. It proves that configured
default metadata selects the initial sink and `target.object` moves the stream
to the second sink while every resulting link remains WirePlumber-owned. Raw
links are therefore an advanced topology tool, not the default routing path.

## Versioning policy

Additive fields or value types that older v1 consumers can safely ignore require careful coordination because the current decoder intentionally rejects unknown fields. They can be introduced within v1 only alongside an explicit negotiated decoder policy. Any incompatible field meaning, identity rule, event ordering rule, mutation behavior, or WirePlumber family change requires a new orchestration contract version.

The runtime-value `schema_version` and orchestration contract version are independent numbers. A future contract may continue using the same value schema or introduce a new one. Consumers must check the orchestration contract before decoding runtime state.
