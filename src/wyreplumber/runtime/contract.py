"""Published compatibility metadata for the orchestration runtime API."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import RUNTIME_VALUE_SCHEMA_VERSION


ORCHESTRATION_CONTRACT_VERSION = 1
WIREPLUMBER_API_FAMILY = "0.5"
ORCHESTRATION_CONTRACT_STABILITY = "development"


class OrchestrationContractCompatibilityError(RuntimeError):
    """The installed binding cannot satisfy a consumer contract range."""

    def __init__(
        self,
        *,
        installed: int,
        minimum: int,
        maximum: int,
    ) -> None:
        self.installed = installed
        self.minimum = minimum
        self.maximum = maximum
        super().__init__(
            "incompatible WyrePlumber orchestration contract: "
            f"consumer requires {minimum}..{maximum}, binding provides {installed}"
        )


@dataclass(frozen=True, slots=True)
class OrchestrationContractInfo:
    """Machine-readable description of the public orchestration boundary."""

    version: int
    runtime_value_schema_version: int
    wireplumber_api_family: str
    stability: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


ORCHESTRATION_CONTRACT = OrchestrationContractInfo(
    version=ORCHESTRATION_CONTRACT_VERSION,
    runtime_value_schema_version=RUNTIME_VALUE_SCHEMA_VERSION,
    wireplumber_api_family=WIREPLUMBER_API_FAMILY,
    stability=ORCHESTRATION_CONTRACT_STABILITY,
)


def require_orchestration_contract(
    minimum: int,
    maximum: int | None = None,
) -> OrchestrationContractInfo:
    """Return contract metadata or fail when version 1 is outside the range."""

    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError("minimum contract version must be a positive integer")
    if maximum is None:
        maximum = minimum
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < minimum:
        raise ValueError("maximum contract version must be an integer not below minimum")
    if not minimum <= ORCHESTRATION_CONTRACT_VERSION <= maximum:
        raise OrchestrationContractCompatibilityError(
            installed=ORCHESTRATION_CONTRACT_VERSION,
            minimum=minimum,
            maximum=maximum,
        )
    return ORCHESTRATION_CONTRACT
