"""
SPA Pod Parser - Convert PipeWire SPA pods to Python types.

This module parses SPA (Simple Plugin API) pods from PipeWire/WirePlumber
into native Python data structures.
"""

import struct
from typing import Any, List, Dict, Optional, Tuple


# SPA Type constants
SPA_TYPE_None = 1
SPA_TYPE_Bool = 2
SPA_TYPE_Id = 3
SPA_TYPE_Int = 4
SPA_TYPE_Long = 5
SPA_TYPE_Float = 6
SPA_TYPE_Double = 7
SPA_TYPE_String = 8
SPA_TYPE_Bytes = 9
SPA_TYPE_Rectangle = 10
SPA_TYPE_Fraction = 11
SPA_TYPE_Bitmap = 12
SPA_TYPE_Array = 13
SPA_TYPE_Struct = 14
SPA_TYPE_Object = 15
SPA_TYPE_Sequence = 16
SPA_TYPE_Pointer = 17
SPA_TYPE_Fd = 18
SPA_TYPE_Choice = 19
SPA_TYPE_Pod = 20

# SPA Choice Type constants
SPA_CHOICE_None = 0
SPA_CHOICE_Range = 1
SPA_CHOICE_Step = 2
SPA_CHOICE_Enum = 3
SPA_CHOICE_Flags = 4


def _align(value: int, alignment: int = 8) -> int:
    """Align a value to the specified alignment."""
    return (value + alignment - 1) & ~(alignment - 1)


def _parse_pod_header(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Parse SPA pod header and return (size, type)."""
    if len(data) < offset + 8:
        raise ValueError("Data too short for SPA pod header")

    size, pod_type = struct.unpack_from('<II', data, offset)
    return size, pod_type


def parse_spa_pod(data: bytes, offset: int = 0) -> Any:
    """
    Parse a SPA pod from bytes and return a Python representation.

    Args:
        data: The bytes containing the SPA pod
        offset: Offset in the data where the pod starts

    Returns:
        Python representation of the pod value
    """
    size, pod_type = _parse_pod_header(data, offset)
    value_offset = offset + 8  # After header

    if pod_type == SPA_TYPE_None:
        return None

    elif pod_type == SPA_TYPE_Bool:
        value = struct.unpack_from('<i', data, value_offset)[0]
        return bool(value)

    elif pod_type == SPA_TYPE_Id:
        return struct.unpack_from('<I', data, value_offset)[0]

    elif pod_type == SPA_TYPE_Int:
        return struct.unpack_from('<i', data, value_offset)[0]

    elif pod_type == SPA_TYPE_Long:
        return struct.unpack_from('<q', data, value_offset)[0]

    elif pod_type == SPA_TYPE_Float:
        return struct.unpack_from('<f', data, value_offset)[0]

    elif pod_type == SPA_TYPE_Double:
        return struct.unpack_from('<d', data, value_offset)[0]

    elif pod_type == SPA_TYPE_String:
        # Null-terminated string
        string_data = data[value_offset:value_offset + size]
        # Remove null terminator if present
        if b'\x00' in string_data:
            string_data = string_data[:string_data.index(b'\x00')]
        return string_data.decode('utf-8', errors='replace')

    elif pod_type == SPA_TYPE_Bytes:
        return data[value_offset:value_offset + size]

    elif pod_type == SPA_TYPE_Rectangle:
        width, height = struct.unpack_from('<II', data, value_offset)
        return {'width': width, 'height': height}

    elif pod_type == SPA_TYPE_Fraction:
        num, denom = struct.unpack_from('<II', data, value_offset)
        return {'num': num, 'denom': denom}

    elif pod_type == SPA_TYPE_Array:
        return _parse_array(data, value_offset, size)

    elif pod_type == SPA_TYPE_Struct:
        return _parse_struct(data, value_offset, size)

    elif pod_type == SPA_TYPE_Object:
        return _parse_object(data, value_offset, size)

    elif pod_type == SPA_TYPE_Choice:
        return _parse_choice(data, value_offset, size)

    elif pod_type == SPA_TYPE_Fd:
        return struct.unpack_from('<q', data, value_offset)[0]

    else:
        # Unknown type - return raw bytes
        return {
            '_type': pod_type,
            '_size': size,
            '_data': data[value_offset:value_offset + size]
        }


def _parse_array(data: bytes, offset: int, size: int) -> List[Any]:
    """Parse a SPA array pod."""
    if size < 8:
        return []

    # Array body: child_size (uint32_t), child_type (uint32_t)
    child_size, child_type = struct.unpack_from('<II', data, offset)

    result = []
    current = offset + 8  # After array body
    end = offset + size

    while current + child_size <= end:
        # Parse each element based on child_type
        # Reconstruct a pod header for parsing
        pod_data = struct.pack('<II', child_size, child_type) + data[current:current + child_size]
        value = parse_spa_pod(pod_data, 0)
        result.append(value)
        current += _align(child_size)

    return result


def _parse_struct(data: bytes, offset: int, size: int) -> List[Any]:
    """Parse a SPA struct pod (list of pods)."""
    result = []
    current = offset
    end = offset + size

    while current < end:
        if current + 8 > end:
            break

        pod_size, pod_type = _parse_pod_header(data, current)
        total_size = _align(8 + pod_size)

        if current + total_size > end:
            break

        value = parse_spa_pod(data, current)
        result.append(value)
        current += total_size

    return result


def _parse_object(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    """Parse a SPA object pod."""
    if size < 8:
        return {}

    # Object body: type (uint32_t), id (uint32_t)
    obj_type, obj_id = struct.unpack_from('<II', data, offset)

    result = {
        '_object_type': obj_type,
        '_object_id': obj_id,
        'properties': {}
    }

    current = offset + 8  # After object body
    end = offset + size

    while current < end:
        if current + 16 > end:  # Minimum prop size
            break

        # Property: key (uint32_t), flags (uint32_t), then a pod
        prop_key, prop_flags = struct.unpack_from('<II', data, current)
        current += 8

        if current + 8 > end:
            break

        # Parse the property value pod
        pod_size, pod_type = _parse_pod_header(data, current)
        total_pod_size = _align(8 + pod_size)

        if current + total_pod_size > end:
            break

        value = parse_spa_pod(data, current)
        result['properties'][prop_key] = value
        current += total_pod_size

    return result


def _parse_choice(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    """Parse a SPA choice pod."""
    if size < 16:
        return {}

    # Choice body: type (uint32_t), flags (uint32_t), then child pod(s)
    choice_type, choice_flags = struct.unpack_from('<II', data, offset)

    # Parse the child pods
    values = []
    current = offset + 8
    end = offset + size

    while current < end:
        if current + 8 > end:
            break

        pod_size, pod_type = _parse_pod_header(data, current)
        total_pod_size = _align(8 + pod_size)

        if current + total_pod_size > end:
            break

        value = parse_spa_pod(data, current)
        values.append(value)
        current += total_pod_size

    result = {
        'choice_type': choice_type,
        'values': values
    }

    # Add semantic meaning based on choice type
    if choice_type == SPA_CHOICE_Range and len(values) >= 3:
        result['default'] = values[0]
        result['min'] = values[1]
        result['max'] = values[2]
    elif choice_type == SPA_CHOICE_Step and len(values) >= 4:
        result['default'] = values[0]
        result['min'] = values[1]
        result['max'] = values[2]
        result['step'] = values[3]
    elif choice_type == SPA_CHOICE_Enum and len(values) >= 1:
        result['default'] = values[0]
        result['alternatives'] = values[1:] if len(values) > 1 else []
    elif choice_type == SPA_CHOICE_None and len(values) >= 1:
        result['value'] = values[0]

    return result


def parse_spa_pod_dict(pod_dict: Dict[str, Any]) -> Any:
    """
    Parse a SPA pod from a dictionary with 'type', 'size', and 'data' keys.

    Args:
        pod_dict: Dictionary with keys 'type', 'size', and 'data' (bytes)

    Returns:
        Python representation of the pod value
    """
    if not isinstance(pod_dict, dict):
        return pod_dict

    if 'data' not in pod_dict:
        return pod_dict

    data = pod_dict['data']
    if not isinstance(data, bytes):
        return pod_dict

    try:
        return parse_spa_pod(data, 0)
    except Exception:
        # If parsing fails, return the original dict
        return pod_dict


def build_spa_pod(value: Any, pod_type: Optional[int] = None) -> bytes:
    """
    Build a SPA pod from a Python value.

    Args:
        value: Python value to encode
        pod_type: Optional SPA type to use. If None, type is inferred from value.

    Returns:
        Bytes containing the SPA pod
    """
    if pod_type is None:
        pod_type = _infer_spa_type(value)

    if pod_type == SPA_TYPE_None:
        return struct.pack('<II', 0, SPA_TYPE_None)

    elif pod_type == SPA_TYPE_Bool:
        int_val = 1 if value else 0
        return struct.pack('<IIii', 4, SPA_TYPE_Bool, int_val, 0)

    elif pod_type == SPA_TYPE_Id:
        return struct.pack('<IIIi', 4, SPA_TYPE_Id, int(value), 0)

    elif pod_type == SPA_TYPE_Int:
        return struct.pack('<IIii', 4, SPA_TYPE_Int, int(value), 0)

    elif pod_type == SPA_TYPE_Long:
        return struct.pack('<IIq', 8, SPA_TYPE_Long, int(value))

    elif pod_type == SPA_TYPE_Float:
        return struct.pack('<IIfi', 4, SPA_TYPE_Float, float(value), 0)

    elif pod_type == SPA_TYPE_Double:
        return struct.pack('<IId', 8, SPA_TYPE_Double, float(value))

    elif pod_type == SPA_TYPE_String:
        string_bytes = value.encode('utf-8') + b'\x00'
        size = len(string_bytes)
        # Align to 8 bytes
        padding = (8 - (size % 8)) % 8
        return struct.pack('<II', size, SPA_TYPE_String) + string_bytes + b'\x00' * padding

    elif pod_type == SPA_TYPE_Bytes:
        size = len(value)
        padding = (8 - ((8 + size) % 8)) % 8
        return struct.pack('<II', size, SPA_TYPE_Bytes) + value + b'\x00' * padding

    else:
        raise ValueError(f"Unsupported SPA type for building: {pod_type}")


def _infer_spa_type(value: Any) -> int:
    """Infer the SPA type from a Python value."""
    if value is None:
        return SPA_TYPE_None
    elif isinstance(value, bool):
        return SPA_TYPE_Bool
    elif isinstance(value, int):
        # Use Int for smaller values, Long for larger
        if -2147483648 <= value <= 2147483647:
            return SPA_TYPE_Int
        else:
            return SPA_TYPE_Long
    elif isinstance(value, float):
        return SPA_TYPE_Float
    elif isinstance(value, str):
        return SPA_TYPE_String
    elif isinstance(value, (bytes, bytearray)):
        return SPA_TYPE_Bytes
    else:
        raise ValueError(f"Cannot infer SPA type for value: {type(value)}")


def build_spa_pod_dict(value: Any, pod_type: Optional[int] = None) -> Dict[str, Any]:
    """
    Build a SPA pod dictionary from a Python value.

    Args:
        value: Python value to encode
        pod_type: Optional SPA type to use. If None, type is inferred from value.

    Returns:
        Dictionary with 'type', 'size', and 'data' keys
    """
    data = build_spa_pod(value, pod_type)
    size, spa_type = struct.unpack_from('<II', data, 0)
    return {
        'type': spa_type,
        'size': size,
        'data': data
    }
