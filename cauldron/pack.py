"""Manifest pack/hashing utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
from typing import Dict, List

from .manifest import load_manifest


@dataclass
class BlobUpdate:
    name: str
    file: str
    hash: str
    size_bytes: int


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _collect_updates(manifest: dict, base_dir: Path, create_missing: bool) -> List[BlobUpdate]:
    weights = manifest.get("weights")
    if not isinstance(weights, dict):
        return []
    blobs = weights.get("blobs")
    if not isinstance(blobs, list) or not blobs:
        return []

    updates: List[BlobUpdate] = []
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        name = blob.get("name")
        filename = blob.get("file")
        if not isinstance(name, str) or not isinstance(filename, str):
            continue
        file_path = base_dir / filename
        if not file_path.exists():
            if not create_missing:
                raise FileNotFoundError(f"Weights blob not found: {file_path}")
            size_bytes = blob.get("size_bytes")
            if not isinstance(size_bytes, int) or size_bytes <= 0:
                raise ValueError(f"Missing or invalid size_bytes for {file_path}")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("wb") as handle:
                handle.truncate(size_bytes)
        digest = _sha256_file(file_path)
        updates.append(
            BlobUpdate(
                name=name,
                file=filename,
                hash=digest,
                size_bytes=file_path.stat().st_size,
            )
        )
    return updates


def _extract_blob_name(block: List[str]) -> str | None:
    for line in block:
        match = re.match(r"\s*name\s*=\s*(\"([^\"]*)\"|'([^']*)')", line)
        if match:
            return match.group(2) if match.group(2) is not None else match.group(3)
    return None


def _apply_blob_updates(block: List[str], update: BlobUpdate, update_size: bool) -> List[str]:
    updated: List[str] = []
    found_hash = False
    found_size = False
    indent = None

    for line in block:
        key_match = re.match(r"^(\s*)([A-Za-z0-9_]+)\s*=", line)
        if key_match and indent is None:
            indent = key_match.group(1)

        hash_match = re.match(r"^(\s*)hash\s*=\s*(\"[^\"]*\"|'[^']*')", line)
        if hash_match:
            found_hash = True
            quote = "\"" if hash_match.group(2).startswith("\"") else "'"
            updated.append(f"{hash_match.group(1)}hash = {quote}{update.hash}{quote}")
            continue

        if update_size:
            size_match = re.match(r"^(\s*)size_bytes\s*=", line)
            if size_match:
                found_size = True
                updated.append(f"{size_match.group(1)}size_bytes = {update.size_bytes}")
                continue

        updated.append(line)

    if indent is None:
        indent = ""
    if not found_hash:
        updated.append(f"{indent}hash = \"{update.hash}\"")
    if update_size and not found_size:
        updated.append(f"{indent}size_bytes = {update.size_bytes}")

    return updated


def _update_manifest_text(text: str, updates: Dict[str, BlobUpdate], update_size: bool) -> str:
    if not updates:
        return text

    lines = text.splitlines()
    out: List[str] = []
    block: List[str] = []
    in_blob = False

    def flush_block() -> None:
        nonlocal block
        if not block:
            return
        name = _extract_blob_name(block)
        if name and name in updates:
            out.extend(_apply_blob_updates(block, updates[name], update_size))
        else:
            out.extend(block)
        block = []

    for line in lines:
        if re.match(r"^\s*\[\[weights\.blobs\]\]\s*$", line):
            if in_blob:
                flush_block()
            in_blob = True
            block = [line]
            continue

        if in_blob and re.match(r"^\s*\[", line):
            flush_block()
            in_blob = False
            out.append(line)
            continue

        if in_blob:
            block.append(line)
        else:
            out.append(line)

    if in_blob:
        flush_block()

    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing


def pack_manifest(
    manifest_path: str | Path,
    update_size: bool,
    write: bool,
    create_missing: bool,
) -> List[BlobUpdate]:
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    updates = _collect_updates(manifest, manifest_path.parent, create_missing)
    if not updates:
        return []

    updates_map = {u.name: u for u in updates}
    text = manifest_path.read_text()
    new_text = _update_manifest_text(text, updates_map, update_size)
    if write and new_text != text:
        manifest_path.write_text(new_text)
    return updates
