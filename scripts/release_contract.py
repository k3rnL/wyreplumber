#!/usr/bin/env python3
"""Validate and describe WyrePlumber release artifacts.

The release workflow deliberately uses this repository-owned helper for the
same checks that can be run on a developer machine or on a downloaded release.
It only uses the Python standard library so artifact verification does not
depend on an unpinned helper package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "wyreplumber"
BUILD_API_FAMILY = "0.5"
SUPPORTED_PYTHON_ABIS = ("cp312", "cp313", "cp314")
SUPPORTED_ARCHITECTURES = ("x86_64", "aarch64")
PROVENANCE_SCHEMA = "wyreplumber-release-provenance-v1"


class ReleaseContractError(RuntimeError):
    """Raised when release bytes do not satisfy the published contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseContractError(message)


def project_version(root: Path = PROJECT_ROOT) -> str:
    data = tomllib.loads(root.joinpath("pyproject.toml").read_text())
    version = data["project"]["version"]
    _require(
        isinstance(version, str)
        and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None,
        f"project version is not a three-part release version: {version!r}",
    )
    return version


def verify_tag(version: str, tag: str | None) -> None:
    if tag:
        _require(tag == f"v{version}", f"tag {tag!r} does not match version {version!r}")


def _metadata_version(raw: bytes, *, source: str) -> str:
    metadata = BytesParser().parsebytes(raw)
    name = metadata.get("Name")
    version = metadata.get("Version")
    _require(
        name is not None and name.lower().replace("_", "-") == PROJECT_NAME,
        f"{source} has unexpected package name {name!r}",
    )
    _require(version is not None, f"{source} does not declare a version")
    return version


def verify_wheel(
    path: Path,
    *,
    python_abi: str,
    architecture: str,
    tag: str | None = None,
) -> None:
    version = project_version()
    verify_tag(version, tag)
    _require(path.is_file(), f"wheel does not exist: {path}")
    _require(python_abi in SUPPORTED_PYTHON_ABIS, f"unsupported Python ABI: {python_abi}")
    _require(
        architecture in SUPPORTED_ARCHITECTURES,
        f"unsupported CPU architecture: {architecture}",
    )
    expected_suffix = f"-{python_abi}-{python_abi}-linux_{architecture}.whl"
    _require(
        path.name == f"{PROJECT_NAME}-{version}{expected_suffix}",
        f"wheel name is not target-qualified as expected: {path.name}",
    )

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        _require(len(metadata_names) == 1, "wheel must contain exactly one METADATA file")
        archive_version = _metadata_version(
            archive.read(metadata_names[0]),
            source=path.name,
        )
        _require(
            archive_version == version,
            f"wheel metadata version {archive_version!r} != project version {version!r}",
        )
        required = {
            f"{PROJECT_NAME}/py.typed",
            f"{PROJECT_NAME}/_core.pyi",
        }
        _require(required <= set(names), f"wheel is missing {sorted(required - set(names))}")
        native = [
            name
            for name in names
            if name.startswith(f"{PROJECT_NAME}/_core.") and name.endswith(".so")
        ]
        _require(len(native) == 1, "wheel must contain exactly one native _core extension")
        _require(
            f"cpython-{python_abi.removeprefix('cp')}-{architecture}-linux-gnu.so"
            in native[0],
            f"native extension does not match ABI/architecture: {native[0]}",
        )
        _require(
            any(name.endswith(".dist-info/licenses/LICENSE") for name in names),
            "wheel does not contain the MIT license",
        )


def verify_sdist(path: Path, *, tag: str | None = None) -> None:
    version = project_version()
    verify_tag(version, tag)
    _require(path.is_file(), f"source archive does not exist: {path}")
    expected_name = f"{PROJECT_NAME}-{version}.tar.gz"
    _require(path.name == expected_name, f"unexpected source archive name: {path.name}")
    prefix = f"{PROJECT_NAME}-{version}/"
    required = {
        "LICENSE",
        "MANIFEST.in",
        "README.md",
        "pyproject.toml",
        "setup.py",
        "docs/runtime-contract-v1.md",
        "examples/runtime_orchestration.py",
        "native/wyreplumber.c",
        "native/wp_compat.h",
        "scripts/release_contract.py",
        "src/wyreplumber/__init__.py",
        "src/wyreplumber/py.typed",
    }
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
        missing = {prefix + name for name in required} - names
        _require(not missing, f"source archive is missing {sorted(missing)}")
        member = archive.getmember(prefix + "PKG-INFO")
        extracted = archive.extractfile(member)
        _require(extracted is not None, "source archive PKG-INFO cannot be read")
        archive_version = _metadata_version(extracted.read(), source=path.name)
        _require(
            archive_version == version,
            f"source metadata version {archive_version!r} != project version {version!r}",
        )


def normalize_architecture(value: str) -> str:
    normalized = value.lower()
    aliases = {"amd64": "x86_64", "arm64": "aarch64"}
    return aliases.get(normalized, normalized)


def verify_installed(
    *,
    python_abi: str,
    architecture: str,
    tag: str | None = None,
    check_linkage: bool = False,
) -> None:
    import importlib.metadata

    import wyreplumber
    from wyreplumber import _core

    version = project_version()
    verify_tag(version, tag)
    installed_version = importlib.metadata.version(PROJECT_NAME)
    _require(installed_version == version, "installed metadata and project version differ")
    _require(wyreplumber.__version__ == version, "runtime and project version differ")
    _require(
        wyreplumber.WIREPLUMBER_BUILD_API_FAMILY == BUILD_API_FAMILY,
        "installed native module was not built for WirePlumber 0.5",
    )
    current_abi = f"cp{sys.version_info.major}{sys.version_info.minor}"
    _require(current_abi == python_abi, f"interpreter ABI {current_abi} != {python_abi}")
    current_architecture = normalize_architecture(platform.machine())
    _require(
        current_architecture == architecture,
        f"runtime architecture {current_architecture} != {architecture}",
    )
    module_path = Path(_core.__file__).resolve()
    _require("site-packages" in module_path.parts, "native module was not imported from an installed wheel")

    if check_linkage:
        completed = subprocess.run(
            ["ldd", str(module_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        _require(completed.returncode == 0, f"ldd failed: {completed.stderr.strip()}")
        linkage = completed.stdout
        _require("not found" not in linkage, f"unresolved native dependency:\n{linkage}")
        _require("libwireplumber-0.5.so" in linkage, "WirePlumber 0.5 linkage is missing")
        _require("libwireplumber-0.4.so" not in linkage, "WirePlumber 0.4 linkage is forbidden")
        _require("libpipewire-0.3.so" in linkage, "PipeWire 0.3 linkage is missing")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_artifact(
    artifact: Path,
    *,
    repository: str,
    commit: str,
    ref: str,
    workflow: str,
    run_id: str,
    run_attempt: str,
    server_url: str,
    target: str,
    python_abi: str,
    architecture: str,
) -> tuple[Path, Path]:
    _require(artifact.is_file(), f"artifact does not exist: {artifact}")
    _require(all((repository, commit, ref, workflow, run_id, run_attempt)), "provenance fields must not be empty")
    digest = sha256(artifact)
    checksum_path = artifact.with_name(f"{artifact.name}.sha256")
    provenance_path = artifact.with_name(f"{artifact.name}.provenance.json")
    checksum_path.write_text(f"{digest}  {artifact.name}\n")
    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "artifact": {"filename": artifact.name, "sha256": digest},
        "source": {"repository": repository, "commit": commit, "ref": ref},
        "build": {
            "workflow": workflow,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "url": f"{server_url}/{repository}/actions/runs/{run_id}",
        },
        "target": {
            "name": target,
            "os": "debian-trixie",
            "python_abi": python_abi,
            "architecture": architecture,
            "wireplumber_api_family": BUILD_API_FAMILY,
        },
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    return checksum_path, provenance_path


def verify_record(artifact: Path) -> dict[str, Any]:
    _require(artifact.is_file(), f"artifact does not exist: {artifact}")
    checksum_path = artifact.with_name(f"{artifact.name}.sha256")
    provenance_path = artifact.with_name(f"{artifact.name}.provenance.json")
    _require(checksum_path.is_file(), f"checksum is missing for {artifact.name}")
    _require(provenance_path.is_file(), f"provenance is missing for {artifact.name}")
    digest = sha256(artifact)
    _require(
        checksum_path.read_text() == f"{digest}  {artifact.name}\n",
        f"checksum does not match {artifact.name}",
    )
    provenance = json.loads(provenance_path.read_text())
    _require(provenance.get("schema") == PROVENANCE_SCHEMA, "unknown provenance schema")
    _require(
        provenance.get("artifact") == {"filename": artifact.name, "sha256": digest},
        f"provenance artifact identity does not match {artifact.name}",
    )
    target = provenance.get("target", {})
    _require(target.get("os") == "debian-trixie", "provenance target OS is not Trixie")
    _require(
        target.get("wireplumber_api_family") == BUILD_API_FAMILY,
        "provenance API family is not WirePlumber 0.5",
    )
    source = provenance.get("source", {})
    build = provenance.get("build", {})
    _require(
        all(source.get(name) for name in ("repository", "commit", "ref")),
        "provenance source identity is incomplete",
    )
    _require(
        all(build.get(name) for name in ("workflow", "run_id", "run_attempt", "url")),
        "provenance build identity is incomplete",
    )
    return provenance


def collect_artifacts(
    source: Path,
    destination: Path,
    *,
    tag: str,
    commit: str,
    repository: str,
) -> None:
    _require(source.is_dir(), f"artifact download directory does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    _require(not any(destination.iterdir()), f"release directory is not empty: {destination}")
    artifacts = sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    _require(len(artifacts) == 7, f"expected six wheels and one source archive, found {len(artifacts)}")
    names = [path.name for path in artifacts]
    _require(len(names) == len(set(names)), "downloaded artifacts have duplicate filenames")
    wheels = [path for path in artifacts if path.suffix == ".whl"]
    sdists = [path for path in artifacts if path.name.endswith(".tar.gz")]
    _require(len(wheels) == 6 and len(sdists) == 1, "release artifact matrix is incomplete")

    expected_targets = {
        (python_abi, architecture)
        for python_abi in SUPPORTED_PYTHON_ABIS
        for architecture in SUPPORTED_ARCHITECTURES
    }
    observed_targets: set[tuple[str, str]] = set()
    for wheel in wheels:
        match = re.search(r"-(cp[0-9]+)-\1-linux_(x86_64|aarch64)\.whl$", wheel.name)
        _require(match is not None, f"wheel target cannot be parsed: {wheel.name}")
        target = (match.group(1), match.group(2))
        verify_wheel(wheel, python_abi=target[0], architecture=target[1], tag=tag)
        observed_targets.add(target)
    _require(observed_targets == expected_targets, "wheel matrix has missing or repeated targets")
    verify_sdist(sdists[0], tag=tag)

    for artifact in artifacts:
        provenance = verify_record(artifact)
        _require(
            provenance["source"] == {
                "repository": repository,
                "commit": commit,
                "ref": f"refs/tags/{tag}",
            },
            f"provenance source does not match the release tag for {artifact.name}",
        )
        for path in (
            artifact,
            artifact.with_name(f"{artifact.name}.sha256"),
            artifact.with_name(f"{artifact.name}.provenance.json"),
        ):
            shutil.copy2(path, destination / path.name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    version_parser = commands.add_parser("version")
    version_parser.add_argument("--tag")

    wheel_parser = commands.add_parser("wheel")
    wheel_parser.add_argument("artifact", type=Path)
    wheel_parser.add_argument("--python-abi", required=True)
    wheel_parser.add_argument("--architecture", required=True)
    wheel_parser.add_argument("--tag")

    sdist_parser = commands.add_parser("sdist")
    sdist_parser.add_argument("artifact", type=Path)
    sdist_parser.add_argument("--tag")

    installed_parser = commands.add_parser("installed")
    installed_parser.add_argument("--python-abi", required=True)
    installed_parser.add_argument("--architecture", required=True)
    installed_parser.add_argument("--tag")
    installed_parser.add_argument("--check-linkage", action="store_true")

    record_parser = commands.add_parser("record")
    record_parser.add_argument("artifact", type=Path)
    for name in (
        "repository",
        "commit",
        "ref",
        "workflow",
        "run-id",
        "run-attempt",
        "server-url",
        "target",
        "python-abi",
        "architecture",
    ):
        record_parser.add_argument(f"--{name}", required=True)

    verify_record_parser = commands.add_parser("verify-record")
    verify_record_parser.add_argument("artifact", type=Path)

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("source", type=Path)
    collect_parser.add_argument("destination", type=Path)
    collect_parser.add_argument("--tag", required=True)
    collect_parser.add_argument("--commit", required=True)
    collect_parser.add_argument("--repository", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "version":
            version = project_version()
            verify_tag(version, args.tag)
            print(version)
        elif args.command == "wheel":
            verify_wheel(
                args.artifact,
                python_abi=args.python_abi,
                architecture=args.architecture,
                tag=args.tag,
            )
        elif args.command == "sdist":
            verify_sdist(args.artifact, tag=args.tag)
        elif args.command == "installed":
            verify_installed(
                python_abi=args.python_abi,
                architecture=args.architecture,
                tag=args.tag,
                check_linkage=args.check_linkage,
            )
        elif args.command == "record":
            record_artifact(
                args.artifact,
                repository=args.repository,
                commit=args.commit,
                ref=args.ref,
                workflow=args.workflow,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                server_url=args.server_url,
                target=args.target,
                python_abi=args.python_abi,
                architecture=args.architecture,
            )
        elif args.command == "verify-record":
            verify_record(args.artifact)
        elif args.command == "collect":
            collect_artifacts(
                args.source,
                args.destination,
                tag=args.tag,
                commit=args.commit,
                repository=args.repository,
            )
        else:  # pragma: no cover - argparse prevents this branch
            raise ReleaseContractError(f"unknown command: {args.command}")
    except (OSError, KeyError, ValueError, ReleaseContractError) as error:
        print(f"release contract failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
