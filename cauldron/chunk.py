"""Chunking helpers for weights blobs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .manifest import load_manifest


@dataclass
class ChunkResult:
    source: Path
    chunks: List[Path]


def _chunk_path(base: Path, idx: int, out_dir: Path) -> Path:
    stem = base.stem
    return out_dir / f"{stem}_chunk{idx}.bin"


def chunk_file(path: Path, chunk_size: int, out_dir: Path) -> ChunkResult:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if not path.exists():
        raise FileNotFoundError(f"Weights file not found: {path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: List[Path] = []
    with path.open("rb") as handle:
        idx = 0
        while True:
            data = handle.read(chunk_size)
            if not data:
                break
            out_path = _chunk_path(path, idx, out_dir)
            out_path.write_bytes(data)
            chunks.append(out_path)
            idx += 1
    return ChunkResult(source=path, chunks=chunks)


def chunk_manifest(manifest_path: Path, chunk_size: Optional[int], out_dir: Optional[Path]) -> List[ChunkResult]:
    manifest = load_manifest(manifest_path)
    weights = manifest.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("weights table missing in manifest")
    blobs = weights.get("blobs")
    if not isinstance(blobs, list) or not blobs:
        raise ValueError("weights.blobs missing in manifest")

    results: List[ChunkResult] = []
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        filename = blob.get("file")
        if not isinstance(filename, str):
            continue
        blob_chunk = chunk_size
        if blob_chunk is None:
            blob_chunk = blob.get("chunk_size")
        if not isinstance(blob_chunk, int) or blob_chunk <= 0:
            raise ValueError("chunk_size is required (no valid chunk_size in manifest)")
        weights_path = manifest_path.parent / filename
        target_dir = out_dir or manifest_path.parent
        results.append(chunk_file(weights_path, blob_chunk, target_dir))
    return results
