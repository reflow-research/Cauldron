"""InvokePanel — input-write, invoke, output operations."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Static

from ..commands import (
    cmd_input_write,
    cmd_invoke,
    cmd_output,
    cmd_program_load,
)
from ..widgets.command_list import CommandItem, CommandList
from ..widgets.output_viewer import OutputViewer


_COMMANDS = [
    CommandItem("Write Input", "input-write", "Stage input data to VM"),
    CommandItem("Load Program", "program-load", "Load guest ELF into VM"),
    CommandItem("Invoke", "invoke", "Execute inference on-chain"),
    CommandItem("Read Output", "output", "Read inference output from VM"),
]


class InvokePanel(Widget):
    """Panel for on-chain inference operations."""

    DEFAULT_CSS = """
    InvokePanel {
        height: 1fr;
    }
    InvokePanel #invoke-input-form,
    InvokePanel #invoke-load-form,
    InvokePanel #invoke-run-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    InvokePanel #invoke-input-form.-visible,
    InvokePanel #invoke-load-form.-visible,
    InvokePanel #invoke-run-form.-visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("[#00ffcc bold]INVOKE[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="invoke-commands")

            # Input write form
            with Vertical(id="invoke-input-form"):
                yield Static("[#8892a4]Input data file (JSON)[/]", classes="input-label")
                yield Input(placeholder="path/to/input.json", id="invoke-data-path")
                with Horizontal(classes="form-row"):
                    yield Checkbox("Include header", id="invoke-header", value=False)
                    yield Checkbox("Include CRC", id="invoke-crc", value=False)
                with Horizontal(classes="form-row"):
                    yield Button("Write Input", id="btn-input-write", variant="primary")
                    yield Button("Cancel", id="btn-input-cancel")

            # Program load form
            with Vertical(id="invoke-load-form"):
                yield Static("[#8892a4]Guest ELF path[/]", classes="input-label")
                yield Input(placeholder="guest/target/.../guest", id="invoke-elf-path")
                with Horizontal(classes="form-row"):
                    yield Button("Load Program", id="btn-program-load", variant="primary")
                    yield Button("Cancel", id="btn-load-cancel")

            # Invoke form
            with Vertical(id="invoke-run-form"):
                yield Static("[#8892a4]Instructions budget[/]", classes="input-label")
                yield Input(value="50000", id="invoke-instructions")
                with Horizontal(classes="form-row"):
                    yield Checkbox("Fast mode (skip sim)", id="invoke-fast", value=False)
                with Horizontal(classes="form-row"):
                    yield Button("Invoke", id="btn-invoke-run", variant="primary")
                    yield Button("Cancel", id="btn-invoke-cancel")

            yield OutputViewer(id="invoke-output")

    def on_command_list_selected(self, event: CommandList.Selected) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._notify("[#ff3366]No active project[/]")
            return

        self._hide_all_forms()
        if event.key == "input-write":
            self._show_form("invoke-input-form")
        elif event.key == "program-load":
            self._show_form("invoke-load-form")
        elif event.key == "invoke":
            self._show_form("invoke-run-form")
        elif event.key == "output":
            self._run_output(proj)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-input-write":
            self._run_input_write()
        elif btn == "btn-program-load":
            self._run_program_load()
        elif btn == "btn-invoke-run":
            self._run_invoke()
        elif btn in ("btn-input-cancel", "btn-load-cancel", "btn-invoke-cancel"):
            self._hide_all_forms()

    def _show_form(self, form_id: str) -> None:
        try:
            self.query_one(f"#{form_id}").add_class("-visible")
        except Exception:
            pass

    def _hide_all_forms(self) -> None:
        for fid in ("invoke-input-form", "invoke-load-form", "invoke-run-form"):
            try:
                self.query_one(f"#{fid}").remove_class("-visible")
            except Exception:
                pass

    def _run_input_write(self) -> None:
        proj = self.app.app_state.active_project  # type: ignore[attr-defined]
        if not proj or not proj.accounts_path:
            self._notify("[#ff3366]No accounts file[/]")
            return

        data_val = self.query_one("#invoke-data-path", Input).value.strip()
        if not data_val:
            self._notify("[#ff3366]Enter data file path[/]")
            return

        data_path = Path(data_val).expanduser()
        if not data_path.is_absolute():
            data_path = proj.manifest_path.parent / data_path

        include_header = self.query_one("#invoke-header", Checkbox).value
        include_crc = self.query_one("#invoke-crc", Checkbox).value

        self._log_info(f"Writing input from {data_path.name}...")
        result = cmd_input_write(
            manifest_path=proj.manifest_path,
            accounts_path=proj.accounts_path,
            data_path=data_path,
            include_header=include_header,
            include_crc=include_crc,
        )
        if result.success:
            self._log_success(result.message)
            self._notify(f"[#39ff14]{result.message}[/]")
            self._hide_all_forms()
        else:
            self._log_error(result.message)
            self._notify(f"[#ff3366]{result.message}[/]")

    def _run_program_load(self) -> None:
        proj = self.app.app_state.active_project  # type: ignore[attr-defined]
        if not proj or not proj.accounts_path:
            self._notify("[#ff3366]No accounts file[/]")
            return

        elf_val = self.query_one("#invoke-elf-path", Input).value.strip()
        if not elf_val:
            self._notify("[#ff3366]Enter guest ELF path[/]")
            return

        elf_path = Path(elf_val).expanduser()
        if not elf_path.is_absolute():
            elf_path = proj.manifest_path.parent / elf_path

        self._log_info(f"Loading program {elf_path.name}...")
        result = cmd_program_load(
            program_path=elf_path,
            accounts_path=proj.accounts_path,
        )
        if result.success:
            self._log_success(result.message)
            for line in result.logs:
                self._log_info(f"  {line}")
            self._notify(f"[#39ff14]{result.message}[/]")
            self._hide_all_forms()
        else:
            self._log_error(result.message)
            for line in result.logs:
                self._log_error(f"  {line}")
            self._notify(f"[#ff3366]{result.message}[/]")

    def _run_invoke(self) -> None:
        proj = self.app.app_state.active_project  # type: ignore[attr-defined]
        if not proj or not proj.accounts_path:
            self._notify("[#ff3366]No accounts file[/]")
            return

        try:
            instructions = int(self.query_one("#invoke-instructions", Input).value.strip() or "50000")
        except ValueError:
            self._notify("[#ff3366]Invalid instructions value[/]")
            return

        fast = self.query_one("#invoke-fast", Checkbox).value

        self._log_info("Invoking inference on-chain...")
        result = cmd_invoke(
            accounts_path=proj.accounts_path,
            instructions=instructions,
            fast=fast,
        )
        if result.success:
            self._log_success(result.message)
            sig = result.data.get("signature")
            if sig:
                self._log_info(f"  signature: {sig}")
            for line in result.logs:
                self._log_info(f"  {line}")
            self._notify(f"[#39ff14]{result.message}[/]")
            self._hide_all_forms()
        else:
            self._log_error(result.message)
            for line in result.logs:
                self._log_error(f"  {line}")
            self._notify(f"[#ff3366]{result.message}[/]")

    def _run_output(self, proj) -> None:
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._notify("[#ffaa00]No accounts file. Set up accounts first.[/]")
            return

        self._log_info("Reading output...")
        result = cmd_output(
            manifest_path=proj.manifest_path,
            accounts_path=proj.accounts_path,
        )
        if result.success:
            try:
                viewer = self.query_one("#invoke-output", OutputViewer)
                viewer.display_output(result.data)
            except Exception:
                pass
            self._log_success("Output read successfully")
        else:
            self._notify(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _notify(self, text: str) -> None:
        try:
            self.app.notify(text)
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
