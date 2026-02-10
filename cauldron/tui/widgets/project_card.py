"""ProjectCard — clickable tile for the home screen project grid."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from ..state import ProjectInfo


class ProjectCard(Widget, can_focus=True):
    """Displays a project summary as a clickable card."""

    DEFAULT_CSS = """
    ProjectCard {
        layout: vertical;
        width: 1fr;
        height: 9;
        min-height: 9;
        background: #1a2332;
        border: solid #1a3a4a;
        padding: 0 1;
        margin: 0;
        color: #e0e6f0;
    }
    ProjectCard:hover {
        border: solid #00ffcc;
    }
    ProjectCard:focus {
        border: solid #00ffcc;
    }
    ProjectCard .card-name {
        color: #00ffcc;
        text-style: bold;
    }
    ProjectCard .card-template {
        color: #ff00aa;
    }
    ProjectCard .card-state {
        color: #8892a4;
    }
    ProjectCard .card-path {
        color: #555e6e;
    }
    ProjectCard .card-time {
        color: #555e6e;
    }
    """

    class Selected(Message):
        """Fired when a card is clicked/activated."""

        def __init__(self, project: ProjectInfo) -> None:
            super().__init__()
            self.project = project

    def __init__(self, project: ProjectInfo, **kwargs) -> None:
        extra_classes = kwargs.pop("classes", "")
        merged_classes = "project-card"
        if extra_classes:
            merged_classes = f"{merged_classes} {extra_classes}"
        super().__init__(classes=merged_classes, **kwargs)
        self.project = project

    def compose(self) -> ComposeResult:
        # Disable markup parsing for user/project values so bracket characters
        # in paths or names do not affect rendering.
        project_name = (self.project.name or self.project.path.name or "unnamed-project").strip()
        yield Static(project_name, classes="card-name", markup=False)
        template_label = str(self.project.template or "unknown")
        yield Static(f"template: {template_label}", classes="card-template", markup=False)
        deployment_state = str(self.project.deployment_state or "init")
        yield Static(f"state: {deployment_state}", classes="card-state", markup=False)
        path_short = str(self.project.path)
        if len(path_short) > 38:
            path_short = "..." + path_short[-35:]
        yield Static(path_short, classes="card-path", markup=False)
        time_raw = self.project.last_activity or "—"
        time_label = str(time_raw)
        if len(time_label) > 19:
            time_label = time_label[:19]
        yield Static(time_label, classes="card-time", markup=False)

    def on_click(self) -> None:
        self.post_message(self.Selected(self.project))

    def action_select(self) -> None:
        self.post_message(self.Selected(self.project))

    BINDINGS = [("enter", "select", "Select")]
