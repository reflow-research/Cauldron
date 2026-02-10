"""CauldronHeader — branded neon top bar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


_LOGO = r" CAULDRON "


class CauldronHeader(Widget):
    """Three-line header: logo, project name, cluster badge."""

    DEFAULT_CSS = """
    CauldronHeader {
        dock: top;
        height: 3;
        background: #111827;
        border-bottom: solid #1a3a4a;
        layout: horizontal;
        padding: 0 2;
    }
    CauldronHeader .logo {
        color: #00ffcc;
        text-style: bold;
        width: auto;
        content-align: left middle;
        padding-right: 2;
    }
    CauldronHeader .separator {
        color: #1a3a4a;
        width: 1;
        content-align: center middle;
    }
    CauldronHeader .project {
        color: #ff00aa;
        text-style: bold;
        width: 1fr;
        content-align: left middle;
        padding-left: 2;
    }
    CauldronHeader .cluster {
        color: #00ffcc;
        width: auto;
        content-align: right middle;
    }
    """

    project_name: reactive[str] = reactive("")
    cluster_name: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Static(_LOGO, classes="logo")
        yield Static("|", classes="separator")
        yield Static("", classes="project", id="header-project")
        yield Static("", classes="cluster", id="header-cluster")

    def watch_project_name(self, value: str) -> None:
        try:
            self.query_one("#header-project", Static).update(value)
        except Exception:
            pass

    def watch_cluster_name(self, value: str) -> None:
        try:
            label = f"[{value}]" if value else ""
            self.query_one("#header-cluster", Static).update(label)
        except Exception:
            pass
