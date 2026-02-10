"""ProgressTracker — wizard step progress indicator."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class ProgressTracker(Widget):
    """Horizontal step indicator: grey=pending, green=done, cyan=active."""

    DEFAULT_CSS = """
    ProgressTracker {
        height: 3;
        background: #111827;
        border-bottom: solid #1a3a4a;
        padding: 0 2;
        layout: horizontal;
        content-align: center middle;
    }
    ProgressTracker .pt-step {
        width: auto;
        padding: 0 1;
        color: #1a3a4a;
    }
    ProgressTracker .pt-step.-completed {
        color: #39ff14;
    }
    ProgressTracker .pt-step.-active {
        color: #00ffcc;
        text-style: bold;
    }
    ProgressTracker .pt-step.-failed {
        color: #ff3366;
        text-style: bold;
    }
    ProgressTracker .pt-step.-skipped {
        color: #ffaa00;
    }
    ProgressTracker .pt-connector {
        width: 3;
        color: #1a3a4a;
        content-align: center middle;
    }
    ProgressTracker .pt-connector.-completed {
        color: #39ff14;
    }
    ProgressTracker .pt-connector.-failed {
        color: #ff3366;
    }
    ProgressTracker .pt-connector.-skipped {
        color: #ffaa00;
    }
    """

    current_step: reactive[int] = reactive(0)
    completed_steps: reactive[frozenset[int]] = reactive(frozenset())
    failed_steps: reactive[frozenset[int]] = reactive(frozenset())
    skipped_steps: reactive[frozenset[int]] = reactive(frozenset())

    def __init__(self, steps: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._steps = steps

    def compose(self) -> ComposeResult:
        with Horizontal(classes="pt-bar"):
            for i, name in enumerate(self._steps):
                if i > 0:
                    yield Static("---", classes="pt-connector", id=f"pt-conn-{i}")
                short = name[:12] if len(name) > 12 else name
                yield Static(f"({i}) {short}", classes="pt-step", id=f"pt-step-{i}")

    def watch_current_step(self, value: int) -> None:
        self._refresh_indicators()

    def watch_completed_steps(self, value: frozenset[int]) -> None:
        self._refresh_indicators()

    def watch_failed_steps(self, value: frozenset[int]) -> None:
        self._refresh_indicators()

    def watch_skipped_steps(self, value: frozenset[int]) -> None:
        self._refresh_indicators()

    def _refresh_indicators(self) -> None:
        for i in range(len(self._steps)):
            try:
                step = self.query_one(f"#pt-step-{i}", Static)
                step.remove_class("-completed", "-active", "-failed", "-skipped")
                if i == self.current_step:
                    step.add_class("-active")
                elif i in self.failed_steps:
                    step.add_class("-failed")
                elif i in self.skipped_steps:
                    step.add_class("-skipped")
                elif i in self.completed_steps:
                    step.add_class("-completed")
            except Exception:
                pass
            if i > 0:
                try:
                    conn = self.query_one(f"#pt-conn-{i}", Static)
                    conn.remove_class("-completed", "-failed", "-skipped")
                    prev = i - 1
                    if prev in self.failed_steps:
                        conn.add_class("-failed")
                    elif prev in self.skipped_steps:
                        conn.add_class("-skipped")
                    elif prev in self.completed_steps:
                        conn.add_class("-completed")
                except Exception:
                    pass

    def advance(self) -> None:
        """Mark current step as completed and move to next."""
        self.completed_steps = self.completed_steps | {self.current_step}
        if self.current_step < len(self._steps) - 1:
            self.current_step += 1

    def go_to(self, step: int) -> None:
        """Jump to a specific step."""
        if 0 <= step < len(self._steps):
            self.current_step = step
