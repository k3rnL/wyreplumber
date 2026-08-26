"""Immutable JSON-compatible containers used by the runtime contract."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from enum import Enum
from math import isfinite
from typing import TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str


class FrozenDict(Mapping[str, object]):
    """A recursively immutable mapping with value-based equality and hashing."""

    __slots__ = ("_items", "_hash")

    def __init__(self, values: Mapping[str, object] | None = None) -> None:
        if values is None:
            values = {}
        if not isinstance(values, Mapping):
            raise TypeError("FrozenDict values must be a mapping")

        items: list[tuple[str, object]] = []
        for key, value in values.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            items.append((key, freeze_json(value)))

        object.__setattr__(self, "_items", tuple(items))
        object.__setattr__(self, "_hash", None)

    def __getitem__(self, key: str) -> object:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("FrozenDict is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("FrozenDict is immutable")

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._items)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return NotImplemented

    def __hash__(self) -> int:
        cached = self._hash
        if cached is None:
            cached = hash(tuple(sorted(self._items, key=lambda item: item[0])))
            object.__setattr__(self, "_hash", cached)
        return cached

    def to_dict(self) -> dict[str, object]:
        """Return a detached mutable JSON-compatible representation."""

        return {key: thaw_json(value) for key, value in self._items}


FrozenJson: TypeAlias = JsonScalar | tuple["FrozenJson", ...] | FrozenDict


def freeze_json(value: object) -> FrozenJson:
    """Validate and recursively freeze a JSON-compatible value."""

    if isinstance(value, Enum):
        return freeze_json(value.value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"value of type {type(value).__name__!r} is not JSON-compatible")


def thaw_json(value: object) -> object:
    """Return mutable dictionaries/lists suitable for a JSON encoder."""

    if isinstance(value, FrozenDict):
        return value.to_dict()
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"value of type {type(value).__name__!r} is not frozen JSON")
