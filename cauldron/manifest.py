"""Manifest loading utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def _load_toml_bytes(data: bytes) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    return tomllib.loads(data.decode("utf-8"))


def load_manifest(path: str | Path) -> Dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    data = manifest_path.read_bytes()
    return _load_toml_bytes(data)
