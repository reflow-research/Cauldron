"""Upload helpers wrapping existing Rust examples."""

from __future__ import annotations

import subprocess
from pathlib import Path


def upload_model_chunk(
    chunk_path: Path,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> int:
    if not chunk_path.exists():
        raise FileNotFoundError(f"Chunk not found: {chunk_path}")
    rust_tools = Path(__file__).resolve().parent / "rust_tools"
    chunk_path = chunk_path.resolve()
    cmd = ["cargo", "run", "--bin", "upload_model", "--", str(chunk_path)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.call(cmd, env=env, cwd=str(rust_tools))


def upload_all_chunks(
    pattern: str,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> int:
    import glob

    chunks = sorted(glob.glob(pattern))
    if not chunks:
        raise FileNotFoundError(f"No chunks found for pattern: {pattern}")
    status = 0
    for path in chunks:
        rc = upload_model_chunk(Path(path), extra_args=extra_args, env=env)
        if rc != 0:
            status = rc
    return status
