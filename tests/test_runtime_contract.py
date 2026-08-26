import os

import pytest

import wyreplumber
from wyreplumber._core import WPConnection
from wyreplumber.runtime import (
    ORCHESTRATION_CONTRACT,
    ORCHESTRATION_CONTRACT_STABILITY,
    ORCHESTRATION_CONTRACT_VERSION,
    RUNTIME_VALUE_SCHEMA_VERSION,
    WIREPLUMBER_API_FAMILY,
    OrchestrationContractCompatibilityError,
    capture_runtime_snapshot,
    require_orchestration_contract,
)


def test_contract_v1_metadata_is_public_and_machine_readable():
    assert ORCHESTRATION_CONTRACT_VERSION == 1
    assert RUNTIME_VALUE_SCHEMA_VERSION == 1
    assert WIREPLUMBER_API_FAMILY == "0.5"
    assert ORCHESTRATION_CONTRACT_STABILITY == "development"
    assert ORCHESTRATION_CONTRACT.to_dict() == {
        "version": 1,
        "runtime_value_schema_version": 1,
        "wireplumber_api_family": "0.5",
        "stability": "development",
    }
    assert wyreplumber.ORCHESTRATION_CONTRACT_VERSION == 1
    assert wyreplumber.ORCHESTRATION_CONTRACT is ORCHESTRATION_CONTRACT
    assert wyreplumber.WIREPLUMBER_BUILD_API_FAMILY in {"0.4", "0.5"}


@pytest.mark.skipif(
    os.environ.get("WYREPLUMBER_RELEASE_GATE") != "1",
    reason="strict native-family assertion is enabled by release CI",
)
def test_release_gate_requires_a_real_wireplumber_0_5_runtime(pipewire_socket):
    assert wyreplumber.WIREPLUMBER_BUILD_API_FAMILY == "0.5"
    health = capture_runtime_snapshot(WPConnection()).health
    assert health.details["wireplumber_api_version"] == "0.5"
    assert health.details["wireplumber_library_version"].startswith("0.5.")


def test_consumer_can_require_an_accepted_contract_range():
    assert require_orchestration_contract(1) is ORCHESTRATION_CONTRACT
    assert require_orchestration_contract(1, 2) is ORCHESTRATION_CONTRACT
    assert wyreplumber.require_orchestration_contract(1) is ORCHESTRATION_CONTRACT


@pytest.mark.parametrize(("minimum", "maximum"), ((2, 2), (3, 5)))
def test_consumer_rejects_an_incompatible_contract_range(minimum, maximum):
    with pytest.raises(OrchestrationContractCompatibilityError) as error:
        require_orchestration_contract(minimum, maximum)

    assert error.value.installed == 1
    assert error.value.minimum == minimum
    assert error.value.maximum == maximum
    assert "binding provides 1" in str(error.value)


@pytest.mark.parametrize(("minimum", "maximum"), ((0, None), (True, None), (2, 1)))
def test_invalid_consumer_ranges_are_rejected(minimum, maximum):
    with pytest.raises(ValueError):
        require_orchestration_contract(minimum, maximum)
