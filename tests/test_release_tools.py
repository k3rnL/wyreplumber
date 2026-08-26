import importlib.metadata
import json

import pytest

import wyreplumber
from scripts import release_contract


def test_runtime_version_matches_distribution_metadata():
    assert wyreplumber.__version__ == importlib.metadata.version("wyreplumber")
    assert wyreplumber.__version__ == release_contract.project_version()


def test_release_matrix_is_explicit_and_includes_the_appliance_target():
    assert release_contract.SUPPORTED_PYTHON_ABIS == ("cp312", "cp313", "cp314")
    assert release_contract.SUPPORTED_ARCHITECTURES == ("x86_64", "aarch64")
    assert release_contract.BUILD_API_FAMILY == "0.5"


def test_tag_must_agree_with_package_version():
    version = release_contract.project_version()
    release_contract.verify_tag(version, f"v{version}")

    with pytest.raises(release_contract.ReleaseContractError, match="does not match"):
        release_contract.verify_tag(version, "v999.0.0")


def test_portable_artifact_record_detects_changed_bytes(tmp_path):
    artifact = tmp_path / "example.whl"
    artifact.write_bytes(b"release bytes")
    checksum, provenance = release_contract.record_artifact(
        artifact,
        repository="k3rnL/wyreplumber",
        commit="0123456789abcdef",
        ref="refs/tags/v0.1.0",
        workflow="CI and release",
        run_id="123",
        run_attempt="1",
        server_url="https://github.com",
        target="cp312-x86_64",
        python_abi="cp312",
        architecture="x86_64",
    )

    record = release_contract.verify_record(artifact)
    assert checksum.read_text().endswith("  example.whl\n")
    assert json.loads(provenance.read_text()) == record
    assert str(tmp_path) not in provenance.read_text()

    artifact.write_bytes(b"changed release bytes")
    with pytest.raises(release_contract.ReleaseContractError, match="checksum"):
        release_contract.verify_record(artifact)
