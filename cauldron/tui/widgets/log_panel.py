"""LogPanel — scrollable, color-coded operation log."""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import RichLog


class LogPanel(RichLog):
    """Scrollable log with color-coded entries for TUI operations."""

    DEFAULT_CSS = """
    LogPanel {
        background: #0a0e17;
        border: solid #1a3a4a;
        padding: 0 1;
        min-height: 6;
        max-height: 50%;
    }
    LogPanel:focus {
        border: solid #00ffcc;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)

    def log_info(self, message: str) -> None:
        self.write(f"[#8892a4]{escape(message)}[/]")

    def log_success(self, message: str) -> None:
        self.write(f"[#39ff14]{escape(message)}[/]")

    def log_error(self, message: str) -> None:
        self.write(f"[#ff3366]{escape(message)}[/]")

    def log_warning(self, message: str) -> None:
        self.write(f"[#ffaa00]{escape(message)}[/]")

    def log_tx(self, message: str) -> None:
        self.write(f"[#00ffcc]{escape(message)}[/]")
