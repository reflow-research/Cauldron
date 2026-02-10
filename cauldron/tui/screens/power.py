"""PowerScreen — panel-based power-user mode with sidebar navigation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, Static

from ..agent_context import copy_text_to_clipboard, render_agent_context, write_agent_context
from ..widgets.header import CauldronHeader
from ..widgets.log_panel import LogPanel
from ..widgets.sidebar import Sidebar
from ..widgets.status_bar import StatusBar
from ..panels.models import ModelsPanel
from ..panels.weights import WeightsPanel
from ..panels.accounts import AccountsPanel
from ..panels.invoke import InvokePanel
from ..panels.train import TrainPanel


class PowerScreen(Screen):
    """Power-user mode with sidebar navigation and action panels."""

    BINDINGS = [
        Binding("1", "switch_panel('models')", "Models", show=False),
        Binding("2", "switch_panel('weights')", "Weights", show=False),
        Binding("3", "switch_panel('accounts')", "Accounts", show=False),
        Binding("4", "switch_panel('invoke')", "Invoke", show=False),
        Binding("5", "switch_panel('train')", "Train", show=False),
        Binding("c", "copy_context", "Copy Context", show=False),
        Binding("escape", "go_home", "Home"),
    ]

    def compose(self) -> ComposeResult:
        header = CauldronHeader()
        app_state = self.app.app_state  # type: ignore[attr-defined]
        if app_state.active_project:
            header.project_name = app_state.active_project.name
            header.cluster_name = app_state.active_project.cluster or "devnet"
        yield header

        with Horizontal(id="power-layout"):
            yield Sidebar(id="power-sidebar")

            with Vertical(id="power-content"):
                with ContentSwitcher(id="panel-switcher", initial="models"):
                    yield ModelsPanel(id="models")
                    yield WeightsPanel(id="weights")
                    yield AccountsPanel(id="accounts")
                    yield InvokePanel(id="invoke")
                    yield TrainPanel(id="train")

                yield Static(
                    "[#1a3a4a]─── LOG ─────────────────────────────────────────[/]",
                    id="log-divider",
                )
                yield LogPanel(id="power-log")

        sb = StatusBar()
        if app_state.active_project:
            sb.project = app_state.active_project.name
            sb.cluster = app_state.active_project.cluster or "devnet"
        yield sb
        yield Footer()

    def on_mount(self) -> None:
        self.get_log().log_info("Power mode active. Use sidebar or keys 1-5 to navigate panels.")

    def on_sidebar_panel_selected(self, event: Sidebar.PanelSelected) -> None:
        self._switch_to(event.panel_id)

    def action_switch_panel(self, panel_id: str) -> None:
        self._switch_to(panel_id)

    def _switch_to(self, panel_id: str) -> None:
        try:
            switcher = self.query_one("#panel-switcher", ContentSwitcher)
            switcher.current = panel_id
            sidebar = self.query_one("#power-sidebar", Sidebar)
            sidebar.active_panel = panel_id
            self._update_status_op(panel_id)
        except Exception:
            pass

    def _update_status_op(self, panel_id: str) -> None:
        try:
            sb = self.query_one(StatusBar)
            sb.operation = panel_id.upper()
        except Exception:
            pass

    def action_go_home(self) -> None:
        if hasattr(self.app, "action_home"):
            self.app.action_home()
        else:
            self.app.pop_screen()

    def _snapshot_log_lines(self, limit: int = 80) -> list[str]:
        try:
            lines = []
            for strip in list(self.get_log().lines)[-limit:]:
                try:
                    text = "".join(segment.text for segment in strip)
                except Exception:
                    text = str(strip)
                if text.strip():
                    lines.append(text.rstrip())
            return lines
        except Exception:
            return []

    def export_agent_context_payload(self) -> dict:
        panel = None
        try:
            panel = self.query_one("#panel-switcher", ContentSwitcher).current
        except Exception:
            pass
        return {
            "source": "power",
            "current_panel": panel,
            "logs": self._snapshot_log_lines(),
        }

    def action_copy_context(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self.app.notify("No active project", severity="warning")
            return
        payload = self.export_agent_context_payload()
        context_text = render_agent_context(project=proj, **payload)
        out_path = write_agent_context(proj.path, context_text)
        copied, tool_msg = copy_text_to_clipboard(context_text)
        if copied:
            self.app.notify(f"Agent context saved and copied ({tool_msg})", severity="information")
            self.get_log().log_success(f"Agent context copied ({tool_msg}): {out_path}")
        else:
            self.app.notify(f"Agent context saved ({tool_msg})", severity="warning")
            self.get_log().log_warning(f"Agent context saved (clipboard unavailable): {out_path}")

    def get_log(self) -> LogPanel:
        return self.query_one("#power-log", LogPanel)
