"""Sidebar — navigation rail for power-user mode."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


_ICONS = {
    "models": "[#00ffcc]>[/]",
    "weights": "[#ff00aa]>[/]",
    "accounts": "[#39ff14]>[/]",
    "invoke": "[#ffaa00]>[/]",
    "train": "[#ff3366]>[/]",
}


class NavItem(Widget, can_focus=True):
    """A single navigation item in the sidebar."""

    DEFAULT_CSS = """
    NavItem {
        width: 100%;
        height: 3;
        background: transparent;
        color: #8892a4;
        content-align: left middle;
        padding: 0 1;
    }
    NavItem:hover {
        background: #1a2332;
        color: #00ffcc;
    }
    NavItem:focus {
        background: #1a2332;
        color: #00ffcc;
    }
    NavItem.-active {
        background: #0a2a3a;
        color: #00ffcc;
        text-style: bold;
        border-left: outer #00ffcc;
    }
    """

    BINDINGS = [("enter", "activate", "Select")]

    class Activated(Message):
        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, label: str, key: str, hotkey: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._key = key
        self._hotkey = hotkey

    def compose(self) -> ComposeResult:
        icon = _ICONS.get(self._key, ">")
        yield Static(f" {icon} {self._label} [#555e6e]({self._hotkey})[/]")

    def on_click(self) -> None:
        self.post_message(self.Activated(self._key))

    def action_activate(self) -> None:
        self.post_message(self.Activated(self._key))


class Sidebar(Widget):
    """Left navigation rail for the power-user screen."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 26;
        background: #111827;
        border-right: solid #1a3a4a;
        padding: 1 0;
    }
    """

    active_panel: reactive[str] = reactive("models")

    class PanelSelected(Message):
        def __init__(self, panel_id: str) -> None:
            super().__init__()
            self.panel_id = panel_id

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[#8892a4 bold] NAVIGATE[/]", classes="nav-title")
            yield Static("")
            yield NavItem("Models", "models", "1", id="nav-models")
            yield NavItem("Weights", "weights", "2", id="nav-weights")
            yield NavItem("Accounts", "accounts", "3", id="nav-accounts")
            yield NavItem("Invoke", "invoke", "4", id="nav-invoke")
            yield NavItem("Train", "train", "5", id="nav-train")
            yield Static("")
            yield Static(
                "[#1a3a4a]────────────────────────[/]",
            )
            yield Static(
                " [#555e6e]Ctrl+P[/] [#8892a4]Palette[/]\n"
                " [#555e6e]Ctrl+H[/] [#8892a4]Home[/]\n"
                " [#555e6e]Esc[/]    [#8892a4]Back[/]",
            )

    def on_mount(self) -> None:
        self._highlight(self.active_panel)

    def on_nav_item_activated(self, event: NavItem.Activated) -> None:
        self.active_panel = event.key
        self.post_message(self.PanelSelected(event.key))

    def watch_active_panel(self, value: str) -> None:
        self._highlight(value)

    def _highlight(self, active_id: str) -> None:
        for key in ("models", "weights", "accounts", "invoke", "train"):
            try:
                item = self.query_one(f"#nav-{key}", NavItem)
                item.remove_class("-active")
                if key == active_id:
                    item.add_class("-active")
            except Exception:
                pass
