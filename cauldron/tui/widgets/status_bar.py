"""StatusBar — bottom bar showing cluster, project, and operation status."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Widget):
    """Single-line status bar at the bottom of the screen."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: #111827;
        border-top: solid #1a3a4a;
        layout: horizontal;
        padding: 0 2;
    }
    StatusBar .cluster-label {
        color: #00ffcc;
        text-style: bold;
        width: auto;
        padding-right: 2;
    }
    StatusBar .project-label {
        color: #ff00aa;
        width: 1fr;
    }
    StatusBar .op-label {
        color: #ffaa00;
        width: auto;
    }
    """

    cluster: reactive[str] = reactive("")
    project: reactive[str] = reactive("")
    operation: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", classes="cluster-label", id="sb-cluster")
        yield Static("", classes="project-label", id="sb-project")
        yield Static("", classes="op-label", id="sb-op")

    def watch_cluster(self, value: str) -> None:
        try:
            self.query_one("#sb-cluster", Static).update(f"[{value}]" if value else "")
        except Exception:
            pass

    def watch_project(self, value: str) -> None:
        try:
            self.query_one("#sb-project", Static).update(value)
        except Exception:
            pass

    def watch_operation(self, value: str) -> None:
        try:
            self.query_one("#sb-op", Static).update(value)
        except Exception:
            pass
