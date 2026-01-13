"""Utility helpers for ModelKit."""

import re
from typing import Iterable


_SLUG_RE = re.compile(r"^[a-z0-9_-]+$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def is_slug(value: str) -> bool:
    return bool(_SLUG_RE.match(value))


def is_semver(value: str) -> bool:
    return bool(_SEMVER_RE.match(value))


def product(values: Iterable[int]) -> int:
    result = 1
    for v in values:
        result *= v
    return result


def ensure_int(value, name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def ensure_str(value, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value
