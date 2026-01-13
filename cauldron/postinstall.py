"""Helper to select and stage the correct on-chain runner binary."""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def _platform_tag() -> str | None:
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


def _runner_name() -> str:
    if platform.system().lower() == "windows":
        return "frostbite-run-onchain.exe"
    return "frostbite-run-onchain"


def _candidates(package_dir: Path) -> list[Path]:
    tag = _platform_tag()
    runner = _runner_name()
    out: list[Path] = []
    if tag:
        out.append(package_dir / "bin" / tag / runner)
        out.append(package_dir / "toolchain" / "bin" / tag / runner)
    out.append(package_dir / "bin" / runner)
    out.append(package_dir / "toolchain" / "bin" / runner)
    return out


def _ensure_executable(path: Path) -> None:
    if platform.system().lower() == "windows":
        return
    mode = path.stat().st_mode
    path.chmod(mode | 0o111)


def main() -> int:
    package_dir = Path(__file__).resolve().parent
    runner = _runner_name()
    dest = package_dir / "bin" / runner
    dest.parent.mkdir(parents=True, exist_ok=True)

    for candidate in _candidates(package_dir):
        if candidate.exists():
            shutil.copy2(candidate, dest)
            _ensure_executable(dest)
            print(dest)
            return 0

    raise SystemExit("No frostbite-run-onchain binary found for this platform")


if __name__ == "__main__":
    raise SystemExit(main())
