"""Cauldron TUI — interactive terminal interface for on-chain AI."""

from __future__ import annotations

from pathlib import Path


def launch_tui(project_path: Path | None = None) -> int:
    """Launch the Cauldron TUI application."""
    from .app import CauldronApp

    app = CauldronApp(project_path=project_path)
    app.run()
    return 0
