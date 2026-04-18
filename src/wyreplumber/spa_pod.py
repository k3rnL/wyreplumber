"""
SPA pod parser/builder for PipeWire and WirePlumber.

The public API intentionally exposes two layers:

- Generic SPA pod helpers such as `parse_spa_pod()` and `build_spa_pod()`.
- Typed Python objects for known SPA object pods, such as `SpaProps` and
  `SpaFormat`, so callers get natural attribute access and IDE completion.

Known object pods support all of these access styles:

- `props.volume`
- `props["volume"]`
- `props[SPA_PROP_volume]`

Unknown object types still fall back to a generic mapping representation so no
raw information is lost.
"""

from __future__ import annotations

from enum import IntEnum
import struct
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ._spa_pod_types import *  # noqa: F401,F403
from ._spa_pod_types import (
    OBJECT_CLASSES_BY_ID,
    SpaPodObject,
    _align,
    _ensure_available,
    _explicit_pod_type,
    _object_param_name,
    _object_type_for_id,
    _pack_pod,
    _parse_pod_header,
    _property_spec_by_key,
    _property_spec_by_name,
)

def parse_spa_pod(data: bytes, offset: int = 0) -> Any:
    """
    Parse a SPA pod from bytes and return a Python representation.

    Scalar pods become plain Python scalars.

    Known SPA object pods are converted into typed Python objects such as
    `SpaProps`, `SpaFormat`, or `SpaParamRoute`, which provide attribute access
    in addition to mapping-style lookup.

    Generic structured pods use dictionaries with a `_pod_type` marker so they
    can be round-tripped back into raw SPA data without losing structure.
    """

    size, pod_type = _parse_pod_header(data, offset)
    value_offset = offset + 8
    _ensure_available(data, value_offset, size)

    if pod_type == SPA_TYPE_None:
        return None
    if pod_type == SPA_TYPE_Bool:
        return bool(struct.unpack_from("<i", data, value_offset)[0])
    if pod_type == SPA_TYPE_Id:
        return struct.unpack_from("<I", data, value_offset)[0]
    if pod_type == SPA_TYPE_Int:
        return struct.unpack_from("<i", data, value_offset)[0]
    if pod_type == SPA_TYPE_Long:
        return struct.unpack_from("<q", data, value_offset)[0]
    if pod_type == SPA_TYPE_Float:
        return struct.unpack_from("<f", data, value_offset)[0]
    if pod_type == SPA_TYPE_Double:
        return struct.unpack_from("<d", data, value_offset)[0]
    if pod_type == SPA_TYPE_String:
        string_data = data[value_offset:value_offset + size]
        if b"\x00" in string_data:
            string_data = string_data.split(b"\x00", 1)[0]
        return string_data.decode("utf-8", errors="replace")
    if pod_type == SPA_TYPE_Bytes:
        return data[value_offset:value_offset + size]
    if pod_type == SPA_TYPE_Rectangle:
        width, height = struct.unpack_from("<II", data, value_offset)
        return {"_pod_type": SPA_TYPE_Rectangle, "width": width, "height": height}
    if pod_type == SPA_TYPE_Fraction:
        num, denom = struct.unpack_from("<II", data, value_offset)
        return {"_pod_type": SPA_TYPE_Fraction, "num": num, "denom": denom}
    if pod_type == SPA_TYPE_Bitmap:
        return {"_pod_type": SPA_TYPE_Bitmap, "data": data[value_offset:value_offset + size]}
    if pod_type == SPA_TYPE_Array:
        return _parse_array(data, value_offset, size)
    if pod_type == SPA_TYPE_Struct:
        return _parse_struct(data, value_offset, size)
    if pod_type == SPA_TYPE_Object:
        return _parse_object(data, value_offset, size)
    if pod_type == SPA_TYPE_Sequence:
        return _parse_sequence(data, value_offset, size)
    if pod_type == SPA_TYPE_Pointer:
        return _parse_pointer(data, value_offset, size)
    if pod_type == SPA_TYPE_Fd:
        return struct.unpack_from("<q", data, value_offset)[0]
    if pod_type == SPA_TYPE_Choice:
        return _parse_choice(data, value_offset, size)
    if pod_type == SPA_TYPE_Pod:
        return _parse_embedded_pod(data, value_offset, size)

    return {
        "_pod_type": pod_type,
        "_type": pod_type,
        "_size": size,
        "_data": data[value_offset:value_offset + size],
    }


def _parse_array(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Array, "child_size": 0, "child_type": SPA_TYPE_None, "values": []}

    child_size, child_type = struct.unpack_from("<II", data, offset)
    values: List[Any] = []
    current = offset + 8
    end = offset + size

    if child_size == 0:
        return {"_pod_type": SPA_TYPE_Array, "child_size": 0, "child_type": child_type, "values": []}

    while current + child_size <= end:
        pod_data = struct.pack("<II", child_size, child_type) + data[current:current + child_size]
        values.append(parse_spa_pod(pod_data, 0))
        current += child_size

    return {
        "_pod_type": SPA_TYPE_Array,
        "child_size": child_size,
        "child_type": child_type,
        "values": values,
    }


def _parse_struct(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    values: List[Any] = []
    current = offset
    end = offset + size

    while current + 8 <= end:
        pod_size, _ = _parse_pod_header(data, current)
        total_size = _align(8 + pod_size)
        if current + total_size > end:
            break
        values.append(parse_spa_pod(data, current))
        current += total_size

    return {"_pod_type": SPA_TYPE_Struct, "values": values}


def _parse_object(data: bytes, offset: int, size: int) -> Any:
    if size < 8:
        return {
            "_pod_type": SPA_TYPE_Object,
            "_object_type": 0,
            "_object_id": 0,
            "object_type": 0,
            "object_id": 0,
            "properties": {},
            "property_flags": {},
            "property_keys": {},
        }

    object_type, object_id = struct.unpack_from("<II", data, offset)
    properties: Dict[Any, Any] = {}
    property_flags: Dict[Any, int] = {}
    property_keys: Dict[str, int] = {}
    current = offset + 8
    end = offset + size

    while current + 16 <= end:
        prop_key, flags = struct.unpack_from("<II", data, current)
        current += 8
        pod_size, _ = _parse_pod_header(data, current)
        total_pod_size = _align(8 + pod_size)
        if current + total_pod_size > end:
            break

        parsed_value = parse_spa_pod(data, current)
        key_name = _resolve_property_name(object_id, prop_key)
        if isinstance(key_name, str):
            parsed_value = _specialize_property_value(object_id, prop_key, parsed_value)
            target_key: Any = key_name
            property_keys[key_name] = prop_key
        else:
            target_key = prop_key

        properties[target_key] = parsed_value
        property_flags[target_key] = flags
        current += total_pod_size

    object_class = OBJECT_CLASSES_BY_ID.get(object_id)
    result = {
        "_pod_type": SPA_TYPE_Object,
        "_object_type": object_type,
        "_object_id": object_id,
        "object_type": object_type,
        "object_id": object_id,
        "properties": properties,
        "property_flags": property_flags,
        "property_keys": property_keys,
    }
    object_name = _object_param_name(object_id)
    if object_name is not None:
        result["object_name"] = object_name
    if object_class is None:
        return result
    return object_class(
        result["properties"],
        property_flags=result["property_flags"],
        property_keys=result["property_keys"],
        object_type=object_type,
        object_id=object_id,
        object_name=object_name,
    )


def _parse_choice(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 16:
        return {
            "_pod_type": SPA_TYPE_Choice,
            "choice_type": SPA_CHOICE_None,
            "flags": 0,
            "child_size": 0,
            "child_type": SPA_TYPE_None,
            "values": [],
        }

    choice_type, flags, child_size, child_type = struct.unpack_from("<IIII", data, offset)
    values: List[Any] = []
    current = offset + 16
    end = offset + size

    if child_size > 0:
        while current + child_size <= end:
            pod_data = struct.pack("<II", child_size, child_type) + data[current:current + child_size]
            values.append(parse_spa_pod(pod_data, 0))
            current += child_size

    result = {
        "_pod_type": SPA_TYPE_Choice,
        "choice_type": choice_type,
        "flags": flags,
        "child_size": child_size,
        "child_type": child_type,
        "values": values,
    }

    if choice_type == SPA_CHOICE_Range and len(values) >= 3:
        result["default"] = values[0]
        result["min"] = values[1]
        result["max"] = values[2]
    elif choice_type == SPA_CHOICE_Step and len(values) >= 4:
        result["default"] = values[0]
        result["min"] = values[1]
        result["max"] = values[2]
        result["step"] = values[3]
    elif choice_type == SPA_CHOICE_Enum and values:
        result["default"] = values[0]
        result["alternatives"] = values[1:]
    elif choice_type == SPA_CHOICE_Flags and values:
        result["default"] = values[0]
        result["flags_values"] = values[1:]
    elif choice_type == SPA_CHOICE_None and values:
        result["value"] = values[0]

    return result


def _parse_sequence(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Sequence, "unit": 0, "controls": []}

    unit = struct.unpack_from("<I", data, offset)[0]
    current = offset + 8
    end = offset + size
    controls = []

    while current + 16 <= end:
        control_offset, control_type = struct.unpack_from("<II", data, current)
        current += 8
        pod_size, _ = _parse_pod_header(data, current)
        total_size = _align(8 + pod_size)
        if current + total_size > end:
            break
        controls.append(
            {
                "offset": control_offset,
                "type": control_type,
                "value": parse_spa_pod(data, current),
            }
        )
        current += total_size

    return {"_pod_type": SPA_TYPE_Sequence, "unit": unit, "controls": controls}


def _parse_pointer(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Pointer, "pointer_type": 0, "value": 0}

    pointer_type = struct.unpack_from("<I", data, offset)[0]
    if size >= 16:
        pointer_value = struct.unpack_from("<Q", data, offset + 8)[0]
    elif size >= 12:
        pointer_value = struct.unpack_from("<I", data, offset + 8)[0]
    else:
        pointer_value = 0

    return {"_pod_type": SPA_TYPE_Pointer, "pointer_type": pointer_type, "value": pointer_value}


def _parse_embedded_pod(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Pod, "pod": None}

    pod_size, _ = _parse_pod_header(data, offset)
    total_size = _align(8 + pod_size)
    if total_size > size:
        raise ValueError("Embedded SPA pod exceeds container size")

    return {
        "_pod_type": SPA_TYPE_Pod,
        "pod": parse_spa_pod(data, offset),
    }


def _resolve_property_name(object_id: int, prop_key: int) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is not None:
        return spec.name
    if object_id in (SPA_PARAM_PeerEnumFormat, SPA_PARAM_PeerCapability):
        return prop_key
    return prop_key


def _specialize_property_value(object_id: int, prop_key: int, value: Any) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is None:
        return value

    if spec.shape == "dict_info":
        return _struct_to_dict_info(value)
    if spec.shape == "params":
        return _struct_to_params(value)
    if spec.shape == "labels":
        return _struct_to_labels(value)
    if spec.shape == "profile_classes":
        return _struct_to_profile_classes(value)
    if spec.shape == "array_int":
        return _array_to_values(value, int)
    if spec.shape == "array_float":
        return _array_to_values(value, float)
    if spec.shape == "array_id":
        values = _array_to_values(value, int)
        if spec.enum_cls is None:
            return values
        return [_coerce_enum_member(item, spec.enum_cls) for item in values]
    if spec.enum_cls is not None:
        return _coerce_enum_property_value(value, spec.enum_cls)
    return value


def _prepare_property_value(object_id: int, prop_key: int, value: Any) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is None:
        return value

    if spec.shape == "dict_info":
        return _dict_info_to_struct(value)
    if spec.shape == "params":
        return _params_to_struct(value)
    if spec.shape == "labels":
        return _labels_to_struct(value)
    if spec.shape == "profile_classes":
        return _profile_classes_to_struct(value)
    if spec.shape == "array_int":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Int, "values": list(value)}
    if spec.shape == "array_float":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Float, "values": list(value)}
    if spec.shape == "array_id":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Id, "values": list(value)}
    if spec.shape == "object_props":
        return _ensure_object_value(value, SPA_TYPE_OBJECT_Props, SPA_PARAM_Props)
    if spec.shape == "object_format":
        return _ensure_object_value(value, SPA_TYPE_OBJECT_Format, SPA_PARAM_Format)
    if spec.enum_cls is not None and isinstance(value, Mapping) and "choice_type" in value:
        prepared_value = dict(value)
        prepared_value.setdefault("child_type", SPA_TYPE_Id)
        return prepared_value
    return value


def _array_to_values(value: Any, convert: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Array:
        return value
    return [convert(item) for item in value.get("values", [])]


def _coerce_enum_member(value: Any, enum_cls: type[IntEnum]) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, int):
        try:
            return enum_cls(value)
        except ValueError:
            return value
    return value


def _coerce_enum_property_value(value: Any, enum_cls: type[IntEnum]) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Choice:
        return _coerce_enum_member(value, enum_cls)

    choice_value = dict(value)
    if "values" in choice_value:
        choice_value["values"] = [_coerce_enum_member(item, enum_cls) for item in choice_value["values"]]
    for key in ("value", "default", "min", "max", "step"):
        if key in choice_value:
            choice_value[key] = _coerce_enum_member(choice_value[key], enum_cls)
    for key in ("alternatives", "flags_values"):
        if key in choice_value:
            choice_value[key] = [_coerce_enum_member(item, enum_cls) for item in choice_value[key]]
    return choice_value


def _struct_to_dict_info(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if not items or not isinstance(items[0], int):
        return value
    count = items[0]
    values = items[1:]
    if len(values) != count * 2 or any(not isinstance(item, str) for item in values):
        return value
    return {values[index]: values[index + 1] for index in range(0, len(values), 2)}


def _dict_info_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Mapping):
        return value
    items: List[Any] = [len(value)]
    for key, item_value in value.items():
        items.extend([str(key), str(item_value)])
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_params(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if len(items) % 2 != 0:
        return value
    params: Dict[str, Any] = {}
    for index in range(0, len(items), 2):
        key = items[index]
        if not isinstance(key, str):
            return value
        params[key] = items[index + 1]
    return params


def _params_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Mapping):
        return value
    items: List[Any] = []
    for key, item_value in value.items():
        items.extend([str(key), item_value])
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_labels(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if len(items) % 2 != 0:
        return value
    labels = []
    for index in range(0, len(items), 2):
        if not isinstance(items[index + 1], str):
            return value
        labels.append({"value": items[index], "label": items[index + 1]})
    return labels


def _labels_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return value
    items: List[Any] = []
    for entry in value:
        if isinstance(entry, Mapping):
            items.extend([entry.get("value"), entry.get("label")])
        elif isinstance(entry, Sequence) and len(entry) == 2:
            items.extend([entry[0], entry[1]])
        else:
            return value
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_profile_classes(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value

    items = list(value.get("values", []))
    if not items or not isinstance(items[0], int):
        return value

    count = items[0]
    classes = []
    nested = items[1:]
    if len(nested) != count:
        return value

    for item in nested:
        if not isinstance(item, Mapping) or item.get("_pod_type") != SPA_TYPE_Struct:
            return value
        entry = list(item.get("values", []))
        if len(entry) != 4 or not isinstance(entry[0], str) or not isinstance(entry[1], int) or not isinstance(entry[2], str):
            return value
        device_indexes = _array_to_values(entry[3], int)
        if not isinstance(device_indexes, list):
            return value
        classes.append(
            {
                "class": entry[0],
                "count": entry[1],
                "property": entry[2],
                "devices": device_indexes,
            }
        )
    return classes


def _profile_classes_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return value
    items: List[Any] = [len(value)]
    for entry in value:
        if not isinstance(entry, Mapping):
            return value
        items.append(
            {
                "_pod_type": SPA_TYPE_Struct,
                "values": [
                    str(entry.get("class")),
                    int(entry.get("count", 0)),
                    str(entry.get("property")),
                    {
                        "_pod_type": SPA_TYPE_Array,
                        "child_type": SPA_TYPE_Int,
                        "values": list(entry.get("devices", [])),
                    },
                ],
            }
        )
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _ensure_object_value(value: Any, object_type: int, object_id: int) -> Any:
    if isinstance(value, SpaPodObject):
        return value
    if isinstance(value, Mapping) and (
        "object_type" in value
        or "_object_type" in value
        or "object_id" in value
        or "_object_id" in value
    ):
        return value
    if isinstance(value, Mapping):
        object_class = OBJECT_CLASSES_BY_ID.get(object_id)
        if object_class is not None:
            return object_class(value, object_type=object_type, object_id=object_id)
        return {
            "_pod_type": SPA_TYPE_Object,
            "_object_type": object_type,
            "_object_id": object_id,
            "object_type": object_type,
            "object_id": object_id,
            "properties": dict(value),
            "property_flags": {},
            "property_keys": {},
        }
    return value


def parse_spa_pod_dict(pod_dict: Dict[str, Any]) -> Any:
    """
    Parse a raw SPA pod dictionary.

    The input is the raw structure returned by the native layer:
    `{'type': int, 'size': int, 'data': bytes}`.
    """
    if not isinstance(pod_dict, dict):
        return pod_dict
    data = pod_dict.get("data")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return pod_dict
    try:
        return parse_spa_pod(bytes(data), 0)
    except Exception:
        return pod_dict


def build_spa_pod(value: Any, pod_type: Optional[int] = None) -> bytes:
    """
    Build a raw SPA pod from a Python value.

    `value` may be a scalar, a generic structured pod mapping, or one of the
    typed SPA object classes defined by this module.
    """

    explicit_type = _explicit_pod_type(value)
    if pod_type is None and explicit_type is not None:
        pod_type = explicit_type
    if pod_type is None:
        pod_type = _infer_spa_type(value)

    if pod_type == SPA_TYPE_None:
        return _pack_pod(SPA_TYPE_None, b"")
    if pod_type == SPA_TYPE_Bool:
        return _pack_pod(SPA_TYPE_Bool, struct.pack("<i", 1 if value else 0))
    if pod_type == SPA_TYPE_Id:
        return _pack_pod(SPA_TYPE_Id, struct.pack("<I", int(value)))
    if pod_type == SPA_TYPE_Int:
        return _pack_pod(SPA_TYPE_Int, struct.pack("<i", int(value)))
    if pod_type == SPA_TYPE_Long:
        return _pack_pod(SPA_TYPE_Long, struct.pack("<q", int(value)))
    if pod_type == SPA_TYPE_Float:
        return _pack_pod(SPA_TYPE_Float, struct.pack("<f", float(value)))
    if pod_type == SPA_TYPE_Double:
        return _pack_pod(SPA_TYPE_Double, struct.pack("<d", float(value)))
    if pod_type == SPA_TYPE_String:
        return _pack_pod(SPA_TYPE_String, str(value).encode("utf-8") + b"\x00")
    if pod_type == SPA_TYPE_Bytes:
        return _pack_pod(SPA_TYPE_Bytes, bytes(value))
    if pod_type == SPA_TYPE_Rectangle:
        width, height = _rectangle_parts(value)
        return _pack_pod(SPA_TYPE_Rectangle, struct.pack("<II", width, height))
    if pod_type == SPA_TYPE_Fraction:
        num, denom = _fraction_parts(value)
        return _pack_pod(SPA_TYPE_Fraction, struct.pack("<II", num, denom))
    if pod_type == SPA_TYPE_Bitmap:
        body = value.get("data") if isinstance(value, Mapping) else value
        return _pack_pod(SPA_TYPE_Bitmap, bytes(body))
    if pod_type == SPA_TYPE_Array:
        return _build_array_pod(value)
    if pod_type == SPA_TYPE_Struct:
        return _build_struct_pod(value)
    if pod_type == SPA_TYPE_Object:
        return _build_object_pod(value)
    if pod_type == SPA_TYPE_Sequence:
        return _build_sequence_pod(value)
    if pod_type == SPA_TYPE_Pointer:
        return _build_pointer_pod(value)
    if pod_type == SPA_TYPE_Fd:
        return _pack_pod(SPA_TYPE_Fd, struct.pack("<q", int(value)))
    if pod_type == SPA_TYPE_Choice:
        return _build_choice_pod(value)
    if pod_type == SPA_TYPE_Pod:
        return _build_embedded_pod(value)

    raise ValueError(f"Unsupported SPA type for building: {pod_type}")


def _rectangle_parts(value: Any) -> Tuple[int, int]:
    if isinstance(value, Mapping):
        return int(value["width"]), int(value["height"])
    if isinstance(value, Sequence) and len(value) == 2:
        return int(value[0]), int(value[1])
    raise ValueError("Rectangle pod expects {'width', 'height'} or a 2-item sequence")


def _fraction_parts(value: Any) -> Tuple[int, int]:
    if isinstance(value, Mapping):
        return int(value["num"]), int(value["denom"])
    if isinstance(value, Sequence) and len(value) == 2:
        return int(value[0]), int(value[1])
    raise ValueError("Fraction pod expects {'num', 'denom'} or a 2-item sequence")


def _build_array_pod(value: Any) -> bytes:
    if isinstance(value, Mapping):
        values = list(value.get("values", []))
        child_type = value.get("child_type")
        child_size = value.get("child_size")
    else:
        values = list(value)
        child_type = None
        child_size = None

    if child_type is None and values:
        child_type = _infer_spa_type(values[0])
    if child_type is None:
        raise ValueError("Array pods require 'child_type' when empty")

    bodies = []
    for item in values:
        pod_bytes = build_spa_pod(item, child_type)
        item_size, item_type = _parse_pod_header(pod_bytes, 0)
        if item_type != child_type:
            raise ValueError("Array items must all use the same child type")
        if child_size is None:
            child_size = item_size
        elif child_size != item_size:
            raise ValueError("Array items must all use the same child size")
        bodies.append(pod_bytes[8:8 + item_size])

    if child_size is None:
        child_size = 0

    body = struct.pack("<II", int(child_size), int(child_type)) + b"".join(bodies)
    return _pack_pod(SPA_TYPE_Array, body)


def _build_struct_pod(value: Any) -> bytes:
    if isinstance(value, Mapping):
        values = list(value.get("values", []))
    else:
        values = list(value)
    body = b"".join(build_spa_pod(item) for item in values)
    return _pack_pod(SPA_TYPE_Struct, body)


def _build_choice_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Choice pods require a mapping with choice metadata")

    values = list(value.get("values", []))
    if not values and "value" in value:
        values = [value["value"]]

    choice_type = int(value.get("choice_type", SPA_CHOICE_None))
    flags = int(value.get("flags", 0))
    child_type = value.get("child_type")
    child_size = value.get("child_size")

    if child_type is None and values:
        child_type = _infer_spa_type(values[0])
    if child_type is None:
        raise ValueError("Choice pods require 'child_type' when empty")

    bodies = []
    for item in values:
        pod_bytes = build_spa_pod(item, child_type)
        item_size, item_type = _parse_pod_header(pod_bytes, 0)
        if item_type != child_type:
            raise ValueError("Choice values must all use the same child type")
        if child_size is None:
            child_size = item_size
        elif child_size != item_size:
            raise ValueError("Choice values must all use the same child size")
        bodies.append(pod_bytes[8:8 + item_size])

    if child_size is None:
        child_size = 0

    body = struct.pack("<IIII", choice_type, flags, int(child_size), int(child_type)) + b"".join(bodies)
    return _pack_pod(SPA_TYPE_Choice, body)


def _build_object_pod(value: Any) -> bytes:
    if isinstance(value, SpaPodObject):
        object_type = value.object_type
        object_id = value.object_id
        properties = dict(value.items())
        property_flags = dict(value.property_flags)
        property_keys = dict(value.property_keys)
    elif isinstance(value, Mapping):
        object_type = value.get("object_type", value.get("_object_type"))
        object_id = value.get("object_id", value.get("_object_id"))
        properties = value.get("properties", {})
        property_flags = value.get("property_flags", {})
        property_keys = value.get("property_keys", {})
    else:
        raise ValueError("Object pods require a mapping")

    if object_id is None:
        raise ValueError("Object pod requires 'object_id'")
    if object_type is None:
        object_type = _object_type_for_id(int(object_id))
    if object_type is None:
        raise ValueError("Object pod requires 'object_type'")

    if not isinstance(properties, Mapping):
        raise ValueError("Object pod 'properties' must be a mapping")

    if not isinstance(property_flags, Mapping):
        property_flags = {}
    if not isinstance(property_keys, Mapping):
        property_keys = {}

    chunks = [struct.pack("<II", int(object_type), int(object_id))]

    for key, raw_value in properties.items():
        if isinstance(key, int):
            prop_key = key
            spec = _property_spec_by_key(int(object_id), prop_key)
            flag_key: Any = key
        else:
            spec = _property_spec_by_name(int(object_id), str(key))
            prop_key = property_keys.get(key)
            if prop_key is None and spec is not None:
                prop_key = spec.key
            if prop_key is None:
                raise ValueError(f"Unknown SPA object property '{key}' for object id {object_id}")
            flag_key = key

        prepared_value = _prepare_property_value(int(object_id), int(prop_key), raw_value)
        nested_type = _explicit_pod_type(prepared_value)
        if nested_type is None and spec is not None:
            nested_type = spec.pod_type

        property_pod = build_spa_pod(prepared_value, nested_type)
        chunks.append(struct.pack("<II", int(prop_key), int(property_flags.get(flag_key, 0))))
        chunks.append(property_pod)

    return _pack_pod(SPA_TYPE_Object, b"".join(chunks))


def _build_sequence_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Sequence pods require a mapping")
    unit = int(value.get("unit", 0))
    controls = value.get("controls", [])
    if not isinstance(controls, Sequence):
        raise ValueError("Sequence pods require a 'controls' sequence")

    chunks = [struct.pack("<II", unit, 0)]
    for control in controls:
        if not isinstance(control, Mapping):
            raise ValueError("Sequence control entries must be mappings")
        control_value = control.get("value")
        control_pod = build_spa_pod(control_value)
        chunks.append(struct.pack("<II", int(control.get("offset", 0)), int(control.get("type", 0))))
        chunks.append(control_pod)
    return _pack_pod(SPA_TYPE_Sequence, b"".join(chunks))


def _build_pointer_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Pointer pods require a mapping")
    pointer_type = int(value.get("pointer_type", 0))
    pointer_value = int(value.get("value", 0))
    return _pack_pod(SPA_TYPE_Pointer, struct.pack("<IIQ", pointer_type, 0, pointer_value))


def _build_embedded_pod(value: Any) -> bytes:
    embedded = value.get("pod") if isinstance(value, Mapping) else value
    if isinstance(embedded, (bytes, bytearray, memoryview)):
        embedded_pod = bytes(embedded)
    else:
        embedded_pod = build_spa_pod(embedded)
    pod_size, _ = _parse_pod_header(embedded_pod, 0)
    total_size = _align(8 + pod_size)
    return _pack_pod(SPA_TYPE_Pod, embedded_pod[:total_size])


def _infer_spa_type(value: Any) -> int:
    explicit_type = _explicit_pod_type(value)
    if explicit_type is not None:
        return explicit_type
    if isinstance(value, SpaPodObject):
        return SPA_TYPE_Object
    if value is None:
        return SPA_TYPE_None
    if isinstance(value, bool):
        return SPA_TYPE_Bool
    if isinstance(value, IntEnum):
        return SPA_TYPE_Id
    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return SPA_TYPE_Int
        return SPA_TYPE_Long
    if isinstance(value, float):
        return SPA_TYPE_Float
    if isinstance(value, str):
        return SPA_TYPE_String
    if isinstance(value, (bytes, bytearray, memoryview)):
        return SPA_TYPE_Bytes
    if isinstance(value, Mapping):
        if "width" in value and "height" in value:
            return SPA_TYPE_Rectangle
        if "num" in value and "denom" in value:
            return SPA_TYPE_Fraction
        if "choice_type" in value:
            return SPA_TYPE_Choice
        if "controls" in value:
            return SPA_TYPE_Sequence
        if "pointer_type" in value:
            return SPA_TYPE_Pointer
        if "object_type" in value or "_object_type" in value or "object_id" in value or "_object_id" in value or "properties" in value:
            return SPA_TYPE_Object
        if "pod" in value:
            return SPA_TYPE_Pod
        if "values" in value and "child_type" in value:
            return SPA_TYPE_Array
        if "values" in value:
            return SPA_TYPE_Struct
    if isinstance(value, Sequence):
        return SPA_TYPE_Struct
    raise ValueError(f"Cannot infer SPA type for value: {type(value)!r}")


def build_spa_pod_dict(value: Any, pod_type: Optional[int] = None) -> Dict[str, Any]:
    """Build a raw `{'type', 'size', 'data'}` SPA pod dictionary."""
    data = build_spa_pod(value, pod_type)
    size, spa_type = _parse_pod_header(data, 0)
    return {"type": spa_type, "size": size, "data": data}
