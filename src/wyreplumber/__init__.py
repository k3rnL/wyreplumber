"""WyrePlumber - Python bindings for WirePlumber."""

from importlib.metadata import version

from . import runtime, spa_pod
from ._core import WIREPLUMBER_BUILD_API_FAMILY
from .runtime import (
    ORCHESTRATION_CONTRACT,
    ORCHESTRATION_CONTRACT_VERSION,
    require_orchestration_contract,
)

__version__ = version("wyreplumber")

__all__ = [
    "ORCHESTRATION_CONTRACT",
    "ORCHESTRATION_CONTRACT_VERSION",
    "WIREPLUMBER_BUILD_API_FAMILY",
    "__version__",
    "require_orchestration_contract",
    "runtime",
    "spa_pod",
]
