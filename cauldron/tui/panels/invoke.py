"""InvokePanel — input-write, invoke, output operations."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Static

from ..commands import (
    cmd_input_write,
    cmd_invoke,
    cmd_output,
)
from ..runtime import resolve_runtime_context
from ..widgets.command_list import CommandItem, CommandList
from ..widgets.output_viewer import OutputViewer


_COMMANDS = [
    CommandItem("Write Input", "input-write", "Stage input data to VM"),
    CommandItem("Invoke", "invoke", "Execute inference on-chain"),
    CommandItem("Read Output", "output", "Read inference output from VM"),
]


class InvokePanel(Widget):
    """Panel for on-chain inference operations."""

    DEFAULT_CSS = """
    InvokePanel {
        height: 1fr;
    }
    InvokePanel #invoke-detail-scroll {
        height: 1fr;
        min-height: 4;
        background: #0a0e17;
        border: solid #1a3a4a;
        padding: 0 1;
    }
    InvokePanel #invoke-input-form,
    InvokePanel #invoke-run-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    InvokePanel #invoke-input-form.-visible,
    InvokePanel #invoke-run-form.-visible {
        display: block;
    }
    InvokePanel #invoke-output {
        margin-top: 1;
        display: none;
    }
    InvokePanel #invoke-output.-visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel", id="invoke-shell"):
            yield Static("[#00ffcc bold]INVOKE[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="invoke-commands")
            with VerticalScroll(id="invoke-detail-scroll"):
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

                # Invoke form
                with Vertical(id="invoke-run-form"):
                    yield Static(
                        "[#8892a4]Instructions budget (press Enter on Invoke to run)[/]",
                        classes="input-label",
                    )
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

        if event.key == "input-write":
            self._show_form("invoke-input-form")
        elif event.key == "invoke":
            self._show_form("invoke-run-form")
        elif event.key == "output":
            self._hide_all_forms()
            self._run_output(proj)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-input-write":
            self._run_input_write()
        elif btn == "btn-invoke-run":
            self._run_invoke()
        elif btn in ("btn-input-cancel", "btn-invoke-cancel"):
            self._hide_all_forms()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        widget_id = event.input.id or ""
        if widget_id == "invoke-data-path":
            self._run_input_write()
        elif widget_id == "invoke-instructions":
            self._run_invoke()

    def _show_form(self, form_id: str) -> None:
        self._hide_all_forms()
        self._set_command_compact(True)
        self._set_output_visible(False)
        try:
            self.query_one(f"#{form_id}").add_class("-visible")
            self.call_after_refresh(self._focus_visible_form_control, form_id)
        except Exception:
            pass

    def _hide_all_forms(self) -> None:
        for fid in ("invoke-input-form", "invoke-run-form"):
            try:
                self.query_one(f"#{fid}").remove_class("-visible")
            except Exception:
                pass
        self._set_command_compact(False)

    def _focus_visible_form_control(self, form_id: str) -> None:
        focus_target = {
            "invoke-input-form": "invoke-data-path",
            # Focus primary action to make Enter immediately actionable.
            "invoke-run-form": "btn-invoke-run",
        }.get(form_id)
        if not focus_target:
            return
        try:
            target = self.query_one(f"#{focus_target}")
            target.focus()
            detail = self.query_one("#invoke-detail-scroll", VerticalScroll)
            detail.scroll_to_widget(target, animate=False, top=True)
        except Exception:
            pass

    def _set_output_visible(self, visible: bool) -> None:
        try:
            viewer = self.query_one("#invoke-output", OutputViewer)
            if visible:
                viewer.add_class("-visible")
                detail = self.query_one("#invoke-detail-scroll", VerticalScroll)
                detail.scroll_to_widget(viewer, animate=False, top=False)
            else:
                viewer.remove_class("-visible")
        except Exception:
            pass

    def _set_command_compact(self, compact: bool) -> None:
        try:
            command_list = self.query_one("#invoke-commands")
            if compact:
                command_list.add_class("-compact")
            else:
                command_list.remove_class("-compact")
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
        runtime = resolve_runtime_context(proj)

        self._log_info(f"Writing input from {data_path.name}...")
        result = cmd_input_write(
            manifest_path=proj.manifest_path,
            accounts_path=proj.accounts_path,
            data_path=data_path,
            include_header=include_header,
            include_crc=include_crc,
            rpc_url=runtime.rpc_url,
            payer=runtime.payer,
            program_id=runtime.program_id,
        )
        if result.success:
            self._log_success(result.message)
            self._notify(f"[#39ff14]{result.message}[/]")
            self._hide_all_forms()
        else:
            self._log_error(result.message)
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
        runtime = resolve_runtime_context(proj)

        self._log_info("Invoking inference on-chain...")
        result = cmd_invoke(
            accounts_path=proj.accounts_path,
            instructions=instructions,
            fast=fast,
            rpc_url=runtime.rpc_url,
            payer=runtime.payer,
            program_id=runtime.program_id,
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
        runtime = resolve_runtime_context(proj)
        result = cmd_output(
            manifest_path=proj.manifest_path,
            accounts_path=proj.accounts_path,
            rpc_url=runtime.rpc_url,
        )
        if result.success:
            try:
                viewer = self.query_one("#invoke-output", OutputViewer)
                viewer.display_output(result.data)
                self._set_output_visible(True)
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
            from ..screens.manual import ManualScreen
            screen = self.screen
            if isinstance(screen, ManualScreen):
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
