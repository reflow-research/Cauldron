#!/usr/bin/env python3
"""Locate the correct frostbite-run-onchain binary for this platform."""

from __future__ import annotations

import argparse
import platform
import shutil
from pathlib import Path


def platform_tag() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "darwin-arm64"
        if machine in {"x86_64", "amd64"}:
            return "darwin-x64"
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "linux-x64"
        if machine in {"arm64", "aarch64"}:
            return "linux-arm64"
    if system == "windows":
        if machine in {"x86_64", "amd64"}:
            return "windows-x64"
    return None


def candidates(root: Path) -> list[Path]:
    tag = platform_tag()
    runner = "frostbite-run-onchain.exe" if platform.system().lower() == "windows" else "frostbite-run-onchain"
    out: list[Path] = []
    if tag:
        out.append(root / "cauldron" / "bin" / tag / runner)
        out.append(root / "cauldron" / "toolchain" / "bin" / tag / runner)
    out.append(root / "cauldron" / "bin" / runner)
    out.append(root / "cauldron" / "toolchain" / "bin" / runner)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", help="Cauldron repo root (defaults to script dir)")
    parser.add_argument("--copy", action="store_true", help="Copy binary to cauldron/bin")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    runner = "frostbite-run-onchain.exe" if platform.system().lower() == "windows" else "frostbite-run-onchain"
    dest = root / "cauldron" / "bin" / runner

    for path in candidates(root):
        if path.exists():
            if args.copy:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                print(dest)
            else:
                print(path)
            return 0

    raise SystemExit("No frostbite-run-onchain binary found for this platform")


if __name__ == "__main__":
    main()
