"""
SPA Pod Parser - Convert PipeWire SPA pods to Python types.

This module parses SPA (Simple Plugin API) pods from PipeWire/WirePlumber
into native Python data structures.
"""

from typing import Any, List, Dict, Optional, Tuple

# SPA Type constants
SPA_TYPE_None: int
SPA_TYPE_Bool: int
SPA_TYPE_Id: int
SPA_TYPE_Int: int
SPA_TYPE_Long: int
SPA_TYPE_Float: int
SPA_TYPE_Double: int
SPA_TYPE_String: int
SPA_TYPE_Bytes: int
SPA_TYPE_Rectangle: int
SPA_TYPE_Fraction: int
SPA_TYPE_Bitmap: int
SPA_TYPE_Array: int
SPA_TYPE_Struct: int
SPA_TYPE_Object: int
SPA_TYPE_Sequence: int
SPA_TYPE_Pointer: int
SPA_TYPE_Fd: int
SPA_TYPE_Choice: int
SPA_TYPE_Pod: int

# SPA Choice Type constants
SPA_CHOICE_None: int
SPA_CHOICE_Range: int
SPA_CHOICE_Step: int
SPA_CHOICE_Enum: int
SPA_CHOICE_Flags: int


def __getattr__(name: str) -> Any:
    ...


def parse_spa_pod(data: bytes, offset: int = 0) -> Any:
    """
    Parse a SPA pod from bytes and return a Python representation.

    Args:
        data: The bytes containing the SPA pod
        offset: Offset in the data where the pod starts (default: 0)

    Returns:
        Python representation of the pod value:
        - None for SPA_TYPE_None
        - bool for SPA_TYPE_Bool
        - int for SPA_TYPE_Id, SPA_TYPE_Int, SPA_TYPE_Long, SPA_TYPE_Fd
        - float for SPA_TYPE_Float, SPA_TYPE_Double
        - str for SPA_TYPE_String
        - bytes for SPA_TYPE_Bytes
        - dict for SPA_TYPE_Rectangle ({'width': int, 'height': int})
        - dict for SPA_TYPE_Fraction ({'num': int, 'denom': int})
        - list for SPA_TYPE_Array, SPA_TYPE_Struct
        - dict for SPA_TYPE_Object ({'_object_type': int, '_object_id': int, 'properties': dict})
        - dict for SPA_TYPE_Choice (see _parse_choice for structure)
        - dict for unknown types ({'_type': int, '_size': int, '_data': bytes})

    Raises:
        ValueError: If data is too short or malformed
    """
    ...


def parse_spa_pod_dict(pod_dict: Dict[str, Any]) -> Any:
    """
    Parse a SPA pod from a dictionary with 'type', 'size', and 'data' keys.

    Args:
        pod_dict: Dictionary with keys 'type', 'size', and 'data' (bytes)

    Returns:
        Python representation of the pod value, or the original dict if parsing fails
    """
    ...


def build_spa_pod(value: Any, pod_type: Optional[int] = None) -> bytes:
    """
    Build a SPA pod from a Python value.

    Args:
        value: Python value to encode (None, bool, int, float, str, bytes)
        pod_type: Optional SPA type to use. If None, type is inferred from value.

    Returns:
        Bytes containing the SPA pod (header + aligned body)

    Raises:
        ValueError: If the value cannot be converted to the specified pod_type,
                   or if pod_type is unsupported for building

    Supported types for building:
        - SPA_TYPE_None: Always returns 0-sized pod
        - SPA_TYPE_Bool: From bool value
        - SPA_TYPE_Id: From int value (unsigned)
        - SPA_TYPE_Int: From int value (signed)
        - SPA_TYPE_Long: From int value (64-bit)
        - SPA_TYPE_Float: From float value (32-bit)
        - SPA_TYPE_Double: From float value (64-bit)
        - SPA_TYPE_String: From str value (null-terminated, 8-byte aligned)
        - SPA_TYPE_Bytes: From bytes/bytearray value (8-byte aligned)
    """
    ...


def build_spa_pod_dict(value: Any, pod_type: Optional[int] = None) -> Dict[str, Any]:
    """
    Build a SPA pod dictionary from a Python value.

    Args:
        value: Python value to encode
        pod_type: Optional SPA type to use. If None, type is inferred from value.

    Returns:
        Dictionary with 'type', 'size', and 'data' keys:
        - 'type': SPA type constant
        - 'size': Size of pod body in bytes (not including header)
        - 'data': Complete pod bytes (header + body)

    Raises:
        ValueError: If the value cannot be converted (see build_spa_pod)
    """
    ...
