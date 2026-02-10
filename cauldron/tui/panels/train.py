"""TrainPanel — training harness interface."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Select, Static

from ..commands import TEMPLATES, cmd_train
from ..widgets.command_list import CommandItem, CommandList


_COMMANDS = [
    CommandItem("Train Model", "train", "Train from data using the manifest template"),
]


class TrainPanel(Widget):
    """Panel for model training."""

    DEFAULT_CSS = """
    TrainPanel {
        height: 1fr;
    }
    TrainPanel #train-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    TrainPanel #train-form.-visible {
        display: block;
    }
    TrainPanel #train-result-scroll {
        height: 1fr;
        min-height: 4;
        background: #0a0e17;
        border: solid #1a3a4a;
        margin-top: 1;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("[#00ffcc bold]TRAIN[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="train-commands")

            with Vertical(id="train-form"):
                yield Static("[#8892a4]Training data (CSV or NPZ)[/]", classes="input-label")
                yield Input(placeholder="path/to/data.csv", id="train-data-path")

                yield Static("[#8892a4]Label column (name or index)[/]", classes="input-label")
                yield Input(placeholder="label or -1", id="train-label-col")

                yield Static("[#8892a4]Task[/]", classes="input-label")
                yield Select(
                    [("regression", "regression"), ("classification", "classification")],
                    value="regression",
                    id="train-task",
                )

                yield Static("[#8892a4]Epochs[/]", classes="input-label")
                yield Input(value="50", id="train-epochs")

                yield Static("[#8892a4]Learning rate[/]", classes="input-label")
                yield Input(value="0.001", id="train-lr")

                yield Static("[#8892a4]Hidden dim (MLP/CNN only)[/]", classes="input-label")
                yield Input(placeholder="auto", id="train-hidden-dim")

                with Horizontal(classes="form-row"):
                    yield Checkbox("No bias", id="train-no-bias", value=False)
                    yield Checkbox("No auto-convert", id="train-no-convert", value=False)

                with Horizontal(classes="form-row"):
                    yield Button("Start Training", id="btn-train-start", variant="primary")
                    yield Button("Cancel", id="btn-train-cancel")

            with VerticalScroll(id="train-result-scroll"):
                yield Static("", id="train-result")

    def on_command_list_selected(self, event: CommandList.Selected) -> None:
        if event.key == "train":
            try:
                self.query_one("#train-form").add_class("-visible")
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-train-start":
            self._run_train()
        elif event.button.id == "btn-train-cancel":
            try:
                self.query_one("#train-form").remove_class("-visible")
            except Exception:
                pass

    def _run_train(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        data_val = self.query_one("#train-data-path", Input).value.strip()
        if not data_val:
            self._show_result("[#ff3366]Enter training data path[/]")
            return

        data_path = Path(data_val).expanduser()
        if not data_path.is_absolute():
            data_path = proj.manifest_path.parent / data_path

        label_col = self.query_one("#train-label-col", Input).value.strip() or None

        task_select = self.query_one("#train-task", Select)
        task = str(task_select.value) if task_select.value != Select.BLANK else "regression"

        try:
            epochs = int(self.query_one("#train-epochs", Input).value.strip() or "50")
        except ValueError:
            epochs = 50

        try:
            lr = float(self.query_one("#train-lr", Input).value.strip() or "0.001")
        except ValueError:
            lr = 0.001

        hidden_val = self.query_one("#train-hidden-dim", Input).value.strip()
        hidden_dim = int(hidden_val) if hidden_val else None

        no_bias = self.query_one("#train-no-bias", Checkbox).value
        no_convert = self.query_one("#train-no-convert", Checkbox).value

        self._show_result("[#ffaa00]Training...[/]")
        self._log_info(f"Training {proj.name} ({epochs} epochs, lr={lr})...")

        result = cmd_train(
            manifest_path=proj.manifest_path,
            data_path=data_path,
            label_col=label_col,
            task=task,
            epochs=epochs,
            lr=lr,
            hidden_dim=hidden_dim,
            no_bias=no_bias,
            no_convert=no_convert,
        )
        if result.success:
            self._show_result(f"[#39ff14]{result.message}[/]")
            self._log_success(result.message)
            try:
                self.query_one("#train-form").remove_class("-visible")
            except Exception:
                pass
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _show_result(self, text: str) -> None:
        try:
            self.query_one("#train-result", Static).update(text)
        except Exception:
            pass

    def _get_log(self):
        try:
            from ..screens.power import PowerScreen
            screen = self.screen
            if isinstance(screen, PowerScreen):
                return screen.get_log()
        except Exception:
            pass
        return None

    def _log_success(self, msg: str) -> None:
        log = self._get_log()
        if log:
            log.log_success(msg)

    def _log_error(self, msg: str) -> None:
        log = self._get_log()
        if log:
            log.log_error(msg)

    def _log_info(self, msg: str) -> None:
        log = self._get_log()
        if log:
            log.log_info(msg)
