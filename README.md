# WyrePlumber

WyrePlumber is a native Python binding for observing and controlling a
PipeWire graph through WirePlumber. It exposes the original low-level proxy API
and an additive orchestration API designed for long-lived consumers such as
Open Cinema.

The orchestration surface provides coherent immutable snapshots, ordered
events with explicit continuity loss, typed parameters and profiles/routes,
confirmed metadata and volume mutations, and ownership-safe managed links.
Its compatibility and lifetime rules are the
[orchestration contract v1](docs/runtime-contract-v1.md). The
[runtime example](examples/runtime_orchestration.py) demonstrates snapshot
bootstrap, event projection, recovery, and a confirmed control.

## Supported release matrix

Release artifacts are native Linux builds with this contract:

| Component | Supported release target |
| --- | --- |
| WirePlumber build and runtime ABI | 0.5 only (`wireplumber-0.5`) |
| PipeWire ABI | 0.3 (`libpipewire-0.3`) |
| Python | CPython 3.12, 3.13, and 3.14 |
| Operating system | Debian 13 (Trixie) |
| Architectures | x86_64 and AArch64 |

Debian Trixie AArch64 is the Open Cinema Raspberry Pi appliance target. A
wheel is specific to one Python ABI and CPU architecture; it is not a portable
pure-Python wheel. `wyreplumber.WIREPLUMBER_BUILD_API_FAMILY` must report
`"0.5"` in production. `wyreplumber.__version__` reports the installed package
version.

WirePlumber 0.4 is not a supported release target. The legacy proxy migration
surface can still be compiled explicitly with `WYREPLUMBER_WP_API=0.4` for
migration investigation, but CI, released wheels, released source archives,
and Open Cinema deployments all require 0.5.

## Install an immutable release

WyrePlumber is currently distributed through
[GitHub Releases](https://github.com/k3rnL/wyreplumber/releases), not PyPI.
Download the wheel matching the interpreter and architecture together with its
`.sha256` and `.provenance.json` files. For example, Python 3.12 on the Pi uses
the filename ending in `cp312-cp312-linux_aarch64.whl`.

Verify the downloaded bytes before installing:

```bash
sha256sum --check wyreplumber-<version>-cp312-cp312-linux_aarch64.whl.sha256
python scripts/release_contract.py verify-record \
  wyreplumber-<version>-cp312-cp312-linux_aarch64.whl
python -m pip install \
  ./wyreplumber-<version>-cp312-cp312-linux_aarch64.whl
```

The verifier is also present in the matching source archive. Open Cinema
release manifests pin the tag, commit, asset URL, and SHA-256 rather than
resolving a moving branch or an adjacent checkout.

The release source archive is installable when the native build requirements
below are present. Verify its adjacent records, extract it if the verifier is
needed, and then let pip build the host-specific wheel:

```bash
sha256sum --check wyreplumber-<version>.tar.gz.sha256
python -m pip install ./wyreplumber-<version>.tar.gz
```

For development, installation from a full immutable commit is supported and
builds against the host's WirePlumber 0.5 headers:

```bash
python -m pip install \
  "wyreplumber @ git+https://github.com/k3rnL/wyreplumber.git@<full-commit-sha>"
```

Do not use `pip install wyreplumber` without an artifact or source URL: no
corresponding PyPI release is currently published.

## Native requirements and permissions

A source build on Trixie needs a C compiler, Python headers, `pkg-config`, and
the PipeWire and WirePlumber 0.5 development packages:

```bash
sudo apt-get install \
  gcc python3-dev pkg-config libpipewire-0.3-dev libwireplumber-0.5-dev
```

Runtime hosts need the matching PipeWire and WirePlumber 0.5 shared libraries.
The binding connects to the native PipeWire socket selected by
`XDG_RUNTIME_DIR`; it does not start or own the system's PipeWire/WirePlumber
services. Run the consumer under the same user session as those services, or
grant that service identity explicit access to the socket. Root is neither
required nor recommended. WirePlumber policy must be running for operations
such as configured defaults and stream targeting to converge.

## Development

Install the Trixie native dependencies above, clone the repository, and create
the locked development environment:

```bash
git clone https://github.com/k3rnL/wyreplumber.git
cd wyreplumber
WYREPLUMBER_WP_API=0.5 uv sync --group dev
```

The default test fixture uses the repository's PipeWire test container. A
fully native test run can instead start a fresh PipeWire and real WirePlumber
0.5 policy process for every live test:

```bash
WYREPLUMBER_WP_API=0.5 \
WYREPLUMBER_SPAWN_PIPEWIRE=1 \
WYREPLUMBER_RELEASE_GATE=1 \
dbus-run-session -- uv run pytest tests/
```

The native fixture configuration starts the real WirePlumber policy process
alongside each isolated PipeWire daemon.

Run a local release-equivalent build and validate its standard archives:

```bash
WYREPLUMBER_WP_API=0.5 uv run --with build python -m build
python scripts/release_contract.py wheel dist/*.whl \
  --python-abi cp312 --architecture x86_64
python scripts/release_contract.py sdist dist/*.tar.gz
uv run --with twine twine check dist/*
```

Adjust the ABI and architecture arguments to the current host. After installing
the wheel in a clean environment, the strict runtime/linkage check is:

```bash
python scripts/release_contract.py installed \
  --python-abi cp312 --architecture x86_64 --check-linkage
```

## Releases

`pyproject.toml` is the version authority. A release uses a `v<version>` Git
tag, for example package version `0.2.0` with tag `v0.2.0`; the workflow rejects
any disagreement before publication. Version changes are made and reviewed in
a normal commit—the workflow never edits or pushes a version.

Every branch and pull request builds one source archive and the complete matrix
of six target-qualified wheels. Each wheel is installed and runs the full test
suite against PipeWire and a real WirePlumber 0.5 process, followed by native
linkage, Python ABI, architecture, package-version, and build-family checks.
The tag job depends on the same gates and publishes each wheel and the single
source archive with per-file SHA-256 and portable JSON provenance records.
Publication requires GitHub's repository immutable-release policy: the workflow
first creates a draft, attaches the complete verified matrix, and only then
publishes it. The published release tag and assets cannot be changed; a failed
release is corrected with a new version rather than a moved tag.

Release procedure:

1. Update `pyproject.toml`, documentation, and any compatibility pins in a
   reviewable release-preparation commit.
2. Run the complete local gate set and push through the repository's normal
   integration branch.
3. After required CI succeeds, create exactly one matching `v<version>` tag.
4. Let the tag workflow publish the assets; never move or reuse a failed tag.
5. Download the published bytes and repeat checksum, provenance, clean-install,
   native linkage, and version checks before accepting them in a deployment
   manifest.

## License

WyrePlumber is released under the MIT License. See [LICENSE](LICENSE).
