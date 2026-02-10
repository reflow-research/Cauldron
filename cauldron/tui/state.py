"""Reactive state containers for the Cauldron TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectInfo:
    """A registered project in the registry."""

    name: str
    path: Path
    manifest_path: Path
    accounts_path: Path | None = None
    template: str | None = None
    cluster: str | None = None
    rpc_url: str | None = None
    program_id: str | None = None
    payer: str | None = None
    last_activity: str | None = None
    deployment_state: str = "init"


@dataclass
class WizardState:
    """Tracks wizard progress and data collected across steps."""

    current_step: int = 0
    workflow_mode: str = "deploy_existing"
    steps_completed: set[int] = field(default_factory=set)
    template: str | None = None
    manifest_path: Path | None = None
    weights_input_path: Path | None = None
    convert_options: dict[str, Any] = field(default_factory=dict)
    guest_built: bool = False
    accounts_path: Path | None = None
    accounts_created: bool = False
    weights_uploaded: bool = False
    input_data_path: Path | None = None
    input_written: bool = False
    program_loaded: bool = False
    invoked: bool = False
    invoke_signature: str | None = None
    output_result: dict[str, Any] | None = None


@dataclass
class LiveOpsState:
    """State for active on-chain operations."""

    active_operation: str | None = None
    progress_pct: float | None = None
    progress_message: str = ""
    logs: list[str] = field(default_factory=list)
    polling: bool = False


class AppState:
    """Central state container for the TUI application."""

    def __init__(self, project_path: Path | None = None) -> None:
        self.projects: list[ProjectInfo] = []
        self.active_project: ProjectInfo | None = None
        self.wizard: WizardState = WizardState()
        self.live_ops: LiveOpsState = LiveOpsState()
        self._initial_project_path = project_path

    def set_active_project(self, project: ProjectInfo) -> None:
        self.active_project = project
        self.wizard = WizardState()
        self.live_ops = LiveOpsState()
