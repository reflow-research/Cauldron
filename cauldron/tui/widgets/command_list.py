"""CommandList — arrow-key navigable action menu."""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import OptionList
from textual.widgets.option_list import Option


@dataclass
class CommandItem:
    """A single command entry."""

    label: str
    key: str
    description: str = ""


class CommandList(Widget):
    """Arrow-key navigable list of commands. Fires Selected on Enter."""

    DEFAULT_CSS = """
    CommandList {
        height: auto;
        background: #111827;
    }
    """

    class Selected(Message):
        """Fired when a command is activated."""

        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, commands: list[CommandItem], **kwargs) -> None:
        super().__init__(**kwargs)
        self._commands = commands

    def compose(self) -> ComposeResult:
        options = [Option(cmd.label, id=cmd.key) for cmd in self._commands]
        yield OptionList(*options)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self.post_message(self.Selected(event.option.id))
