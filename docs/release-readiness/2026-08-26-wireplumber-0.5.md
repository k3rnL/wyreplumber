# WirePlumber 0.5 release-readiness evidence

Date: 2026-08-26

This is pre-version-bump evidence for the WyrePlumber release candidate on the
current x86_64 build host. The repository was on branch
`pipewire-object-refactor` at base commit `e58456f`; the candidate source was a
dirty, uncommitted working tree and is not identified here as a releasable
commit.

## Native environment

The physical development host only provides WirePlumber 0.4 headers. To avoid
silently validating the wrong ABI, the current-host x86_64 build and test were
run in the repository's Debian 13 (Trixie) container environment:

- CPython 3.12.14
- x86_64
- WirePlumber 0.5.8, compiled and linked as 0.5.8
- PipeWire 1.4.2, compiled and linked as 1.4.2

`WYREPLUMBER_WP_API=0.5` was set for every build. The installed wheel reported
package version `0.1.0` (the pre-bump version) and
`WIREPLUMBER_BUILD_API_FAMILY == "0.5"`.

## Artifact validation

The standard build produced:

- `wyreplumber-0.1.0-cp312-cp312-linux_x86_64.whl`
- `wyreplumber-0.1.0.tar.gz`

Both archives passed `twine check` and the repository-owned release-contract
validator. The source validator confirmed the metadata, native sources,
license, type information, orchestration contract, example, and release helper
were present. The wheel was installed with `--no-deps --force-reinstall` into
the clean Trixie container rather than imported from the adjacent `src/`
directory.

The strict installed-artifact check confirmed:

- project metadata, installed metadata, and runtime version agree;
- the interpreter ABI is `cp312` and the architecture is `x86_64`;
- the extension was imported from `site-packages`;
- `libpipewire-0.3.so.0` and `libwireplumber-0.5.so.0` resolve;
- no dependency is missing and no WirePlumber 0.4 library is linked.

## Test result

The installed wheel ran the complete suite against a fresh native PipeWire
daemon and the real WirePlumber process started by the fixture configuration:

```text
205 passed in 5.48s
```

This includes the original proxy tests and the complete orchestration contract
suite: snapshots, ordered events, reconnect/overflow recovery, parameters,
metadata/default/stream targeting, profiles/routes, and managed-link ownership.

## Deferred matrix evidence

The local host cannot execute AArch64 code and does not provide all three
supported CPython interpreters. CPython 3.13/3.14 and Debian Trixie AArch64
(including the Raspberry Pi target) therefore remain CI/release-workflow gates.
No version bump, commit, push, tag, workflow run, or GitHub release was performed
as part of this evidence.
