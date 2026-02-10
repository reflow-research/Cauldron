"""Sidebar — navigation rail for manual mode."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


_PANEL_ORDER = ("models", "train", "weights", "accounts", "invoke")

_ICONS = {
    "models": "[#00ffcc]>[/]",
    "train": "[#ff3366]>[/]",
    "weights": "[#ff00aa]>[/]",
    "accounts": "[#39ff14]>[/]",
    "invoke": "[#ffaa00]>[/]",
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
    """Left navigation rail for the manual screen."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 26;
        background: #111827;
        border-right: solid #1a3a4a;
        padding: 1 0;
    }
    """

    BINDINGS = [
        Binding("up", "nav_prev", "Prev", show=False, priority=True),
        Binding("down", "nav_next", "Next", show=False, priority=True),
        Binding("tab", "nav_next", "Next", show=False, priority=True),
        Binding("shift+tab", "nav_prev", "Prev", show=False, priority=True),
    ]

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
            yield NavItem("Train", "train", "2", id="nav-train")
            yield NavItem("Weights", "weights", "3", id="nav-weights")
            yield NavItem("Accounts", "accounts", "4", id="nav-accounts")
            yield NavItem("Invoke", "invoke", "5", id="nav-invoke")
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
        self.call_after_refresh(self.focus_active_item)

    def on_nav_item_activated(self, event: NavItem.Activated) -> None:
        self.active_panel = event.key
        self.post_message(self.PanelSelected(event.key))

    def watch_active_panel(self, value: str) -> None:
        self._highlight(value)

    def _highlight(self, active_id: str) -> None:
        for key in _PANEL_ORDER:
            try:
                item = self.query_one(f"#nav-{key}", NavItem)
                item.remove_class("-active")
                if key == active_id:
                    item.add_class("-active")
            except Exception:
                pass

    def action_nav_next(self) -> None:
        self._focus_relative(1)

    def action_nav_prev(self) -> None:
        self._focus_relative(-1)

    def focus_active_item(self) -> None:
        self._focus_item(self.active_panel)

    def _focus_relative(self, delta: int) -> None:
        current = self._focused_item_key() or self.active_panel
        try:
            idx = _PANEL_ORDER.index(current)
        except ValueError:
            idx = 0
        next_idx = (idx + delta) % len(_PANEL_ORDER)
        self._focus_item(_PANEL_ORDER[next_idx])

    def _focused_item_key(self) -> str | None:
        for key in _PANEL_ORDER:
            try:
                item = self.query_one(f"#nav-{key}", NavItem)
            except Exception:
                continue
            if item.has_focus:
                return key
        return None

    def _focus_item(self, key: str) -> None:
        try:
            self.query_one(f"#nav-{key}", NavItem).focus()
        except Exception:
            pass
