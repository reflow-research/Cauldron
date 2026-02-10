"""WeightsPanel — convert, pack, chunk operations."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Static

from ..commands import cmd_chunk, cmd_convert, cmd_pack, cmd_upload
from ..runtime import resolve_runtime_context
from ..widgets.command_list import CommandItem, CommandList


_COMMANDS = [
    CommandItem("Convert Weights", "convert", "Convert weights to binary format"),
    CommandItem("Pack Manifest", "pack", "Hash weights and update manifest"),
    CommandItem("Chunk Weights", "chunk", "Split weights for upload"),
    CommandItem("Upload Weights", "upload", "Upload chunk(s) to on-chain weights account"),
]


class WeightsPanel(Widget):
    """Panel for weight conversion and preparation."""

    DEFAULT_CSS = """
    WeightsPanel {
        height: 1fr;
    }
    WeightsPanel #weights-result-scroll {
        height: 1fr;
        min-height: 4;
        background: #0a0e17;
        border: solid #1a3a4a;
        margin-top: 1;
        padding: 0 1;
    }
    WeightsPanel #convert-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    WeightsPanel #convert-form.-visible {
        display: block;
    }
    WeightsPanel #upload-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    WeightsPanel #upload-form.-visible {
        display: block;
    }
    WeightsPanel .form-row {
        height: auto;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("[#00ffcc bold]WEIGHTS[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="weights-commands")

            # Convert form (hidden by default)
            with Vertical(id="convert-form"):
                yield Static("[#8892a4]Weights file path[/]", classes="input-label")
                yield Input(
                    placeholder="path/to/weights.json or .npz",
                    id="convert-input-path",
                )
                with Horizontal(classes="form-row"):
                    yield Checkbox("Auto-pack after convert", id="convert-auto-pack", value=True)
                with Horizontal(classes="form-row"):
                    yield Button("Run Convert", id="btn-convert", variant="primary")
                    yield Button("Cancel", id="btn-convert-cancel")

            # Upload form (hidden by default)
            with Vertical(id="upload-form"):
                yield Static("[#8892a4]Chunk file or glob pattern[/]", classes="input-label")
                yield Input(value="*_chunk*.bin", id="upload-pattern")
                with Horizontal(classes="form-row"):
                    yield Button("Upload Weights", id="btn-upload-weights", variant="primary")
                    yield Button("Cancel", id="btn-upload-cancel")

            with VerticalScroll(id="weights-result-scroll"):
                yield Static("", id="weights-result")

    def on_command_list_selected(self, event: CommandList.Selected) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        manifest = proj.manifest_path

        if event.key == "pack":
            self._hide_forms()
            self._run_pack(manifest)
        elif event.key == "chunk":
            self._hide_forms()
            self._run_chunk(manifest)
        elif event.key == "convert":
            self._show_convert_form()
        elif event.key == "upload":
            self._show_upload_form()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-convert":
            self._run_convert()
        elif event.button.id == "btn-convert-cancel":
            self._hide_convert_form()
        elif event.button.id == "btn-upload-weights":
            self._run_upload()
        elif event.button.id == "btn-upload-cancel":
            self._hide_upload_form()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_id = event.input.id or ""
        if input_id == "convert-input-path":
            self._run_convert()
        elif input_id == "upload-pattern":
            self._run_upload()

    def _show_convert_form(self) -> None:
        self._hide_upload_form()
        self._set_command_compact(True)
        try:
            form = self.query_one("#convert-form")
            form.add_class("-visible")
            self.call_after_refresh(self._focus_convert_input)
        except Exception:
            pass

    def _hide_convert_form(self) -> None:
        try:
            form = self.query_one("#convert-form")
            form.remove_class("-visible")
        except Exception:
            pass
        self._set_command_compact(self._any_form_visible())

    def _show_upload_form(self) -> None:
        self._hide_convert_form()
        self._set_command_compact(True)
        try:
            form = self.query_one("#upload-form")
            form.add_class("-visible")
            self.call_after_refresh(self._focus_upload_input)
        except Exception:
            pass

    def _hide_upload_form(self) -> None:
        try:
            form = self.query_one("#upload-form")
            form.remove_class("-visible")
        except Exception:
            pass
        self._set_command_compact(self._any_form_visible())

    def _hide_forms(self) -> None:
        self._hide_convert_form()
        self._hide_upload_form()

    def _focus_convert_input(self) -> None:
        try:
            self.query_one("#convert-input-path", Input).focus()
        except Exception:
            pass

    def _focus_upload_input(self) -> None:
        try:
            self.query_one("#upload-pattern", Input).focus()
        except Exception:
            pass

    def _any_form_visible(self) -> bool:
        for form_id in ("#convert-form", "#upload-form"):
            try:
                if "-visible" in self.query_one(form_id).classes:
                    return True
            except Exception:
                continue
        return False

    def _set_command_compact(self, compact: bool) -> None:
        try:
            command_list = self.query_one("#weights-commands")
            if compact:
                command_list.add_class("-compact")
            else:
                command_list.remove_class("-compact")
        except Exception:
            pass

    def _run_convert(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        try:
            input_path = self.query_one("#convert-input-path", Input).value.strip()
        except Exception:
            return

        if not input_path:
            self._show_result("[#ff3366]Please enter a weights file path[/]")
            return

        resolved = Path(input_path).expanduser()
        if not resolved.is_absolute():
            resolved = proj.manifest_path.parent / resolved

        try:
            auto_pack = self.query_one("#convert-auto-pack", Checkbox).value
        except Exception:
            auto_pack = False

        self._show_result("[#ffaa00]Converting...[/]")
        self._log_info(f"Converting {resolved.name}...")

        result = cmd_convert(
            manifest_path=proj.manifest_path,
            input_path=resolved,
            auto_pack=auto_pack,
        )
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            for log_entry in result.logs:
                lines.append(f"  [#8892a4]{log_entry}[/]")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
            self._hide_convert_form()
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_upload(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._show_result("[#ffaa00]No accounts file. Run Accounts -> Init/Create first.[/]")
            return

        raw_pattern = self.query_one("#upload-pattern", Input).value.strip()
        if not raw_pattern:
            self._show_result("[#ff3366]Enter chunk path or glob pattern[/]")
            return

        base_dir = proj.manifest_path.parent
        runtime = resolve_runtime_context(proj)
        wildcard = any(ch in raw_pattern for ch in ("*", "?", "["))
        if wildcard:
            pattern_path = Path(raw_pattern).expanduser()
            if pattern_path.is_absolute():
                glob_pattern = str(pattern_path)
            else:
                glob_pattern = str(base_dir / raw_pattern)
            self._show_result(f"[#ffaa00]Uploading chunks: {glob_pattern}[/]")
            self._log_info(f"Uploading chunks matching: {glob_pattern}")
            result = cmd_upload(
                glob_pattern=glob_pattern,
                accounts_path=proj.accounts_path,
                rpc_url=runtime.rpc_url,
                payer=runtime.payer,
                program_id=runtime.program_id,
            )
        else:
            chunk_path = Path(raw_pattern).expanduser()
            if not chunk_path.is_absolute():
                chunk_path = base_dir / chunk_path
            self._show_result(f"[#ffaa00]Uploading chunk: {chunk_path.name}[/]")
            self._log_info(f"Uploading chunk: {chunk_path}")
            result = cmd_upload(
                file_path=chunk_path,
                accounts_path=proj.accounts_path,
                rpc_url=runtime.rpc_url,
                payer=runtime.payer,
                program_id=runtime.program_id,
            )

        if result.success:
            self._show_result(f"[#39ff14]{result.message}[/]")
            self._log_success(result.message)
            self._hide_upload_form()
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_pack(self, manifest) -> None:
        self._show_result("[#ffaa00]Packing...[/]")
        self._log_info("Packing manifest...")
        result = cmd_pack(manifest, update_size=True)
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            updates = result.data.get("updates")
            if updates:
                lines.append(f"  [#8892a4]updates:[/] {updates}")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_chunk(self, manifest) -> None:
        self._show_result("[#ffaa00]Chunking...[/]")
        self._log_info("Chunking weights...")
        result = cmd_chunk(manifest_path=manifest)
        if result.success:
            chunks = result.data.get("chunks")
            lines = [f"[#39ff14]{result.message}[/]"]
            if isinstance(chunks, (list, tuple)):
                lines.append(f"  [#8892a4]chunks created:[/] {len(chunks)}")
                for c in chunks[:10]:
                    lines.append(f"    [#555e6e]{c}[/]")
                if len(chunks) > 10:
                    lines.append(f"    [#555e6e]... and {len(chunks) - 10} more[/]")
            elif chunks:
                lines.append(f"  [#8892a4]result:[/] {chunks}")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _show_result(self, text: str) -> None:
        try:
            self.query_one("#weights-result", Static).update(text)
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
