"""ModelsPanel — validate, show, build-guest, schema-hash."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from ..commands import (
    cmd_build_guest,
    cmd_program_load,
    cmd_schema_hash,
    cmd_show,
    cmd_validate,
)
from ..runtime import resolve_runtime_context
from ..widgets.command_list import CommandItem, CommandList


_COMMANDS = [
    CommandItem("Validate Manifest", "validate", "Check manifest against spec"),
    CommandItem("Show Manifest", "show", "Display manifest sections"),
    CommandItem("Build Guest", "build-guest", "Compile RISC-V guest program"),
    CommandItem("Upload Guest Program", "upload-guest", "Load compiled guest ELF into VM"),
    CommandItem("Schema Hash", "schema-hash", "Compute schema hash"),
]


class ModelsPanel(Widget):
    """Panel for model lifecycle actions."""

    DEFAULT_CSS = """
    ModelsPanel {
        height: 1fr;
    }
    ModelsPanel #models-upload-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    ModelsPanel #models-upload-form.-visible {
        display: block;
    }
    ModelsPanel #models-result-scroll {
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
            yield Static("[#00ffcc bold]MODELS[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="models-commands")
            with Vertical(id="models-upload-form"):
                yield Static("[#8892a4]Guest ELF path[/]", classes="input-label")
                yield Input(
                    placeholder="guest/target/.../release/frostbite-guest",
                    id="models-guest-path",
                )
                with Horizontal(classes="form-row"):
                    yield Button("Upload Guest", id="btn-models-upload-guest", variant="primary")
                    yield Button("Cancel", id="btn-models-upload-cancel")
            with VerticalScroll(id="models-result-scroll"):
                yield Static("", id="models-result")

    def on_command_list_selected(self, event: CommandList.Selected) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        manifest = proj.manifest_path
        if event.key == "validate":
            self._hide_upload_form()
            self._run_validate(manifest)
        elif event.key == "show":
            self._hide_upload_form()
            self._run_show(manifest)
        elif event.key == "build-guest":
            self._hide_upload_form()
            self._run_build_guest(manifest)
        elif event.key == "upload-guest":
            self._show_upload_form(proj)
        elif event.key == "schema-hash":
            self._hide_upload_form()
            self._run_schema_hash(manifest)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-models-upload-guest":
            self._run_upload_guest()
        elif event.button.id == "btn-models-upload-cancel":
            self._hide_upload_form()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if (event.input.id or "") == "models-guest-path":
            self._run_upload_guest()

    def _show_upload_form(self, proj) -> None:
        self._set_command_compact(True)
        try:
            path_input = self.query_one("#models-guest-path", Input)
            if not path_input.value.strip():
                guessed = self._guess_guest_binary_path(proj.manifest_path)
                if guessed:
                    try:
                        path_input.value = str(guessed.relative_to(proj.manifest_path.parent))
                    except Exception:
                        path_input.value = str(guessed)
            self.query_one("#models-upload-form").add_class("-visible")
            self.call_after_refresh(path_input.focus)
        except Exception:
            self._set_command_compact(False)

    def _hide_upload_form(self) -> None:
        try:
            self.query_one("#models-upload-form").remove_class("-visible")
        except Exception:
            pass
        self._set_command_compact(False)

    def _set_command_compact(self, compact: bool) -> None:
        try:
            commands = self.query_one("#models-commands")
            if compact:
                commands.add_class("-compact")
            else:
                commands.remove_class("-compact")
        except Exception:
            pass

    def _guess_guest_binary_path(self, manifest_path: Path) -> Path | None:
        base = manifest_path.parent / "guest" / "target" / "riscv64imac-unknown-none-elf"
        candidates = [
            base / "release" / "frostbite-guest",
            base / "release" / "guest",
            base / "debug" / "frostbite-guest",
            base / "debug" / "guest",
            base / "release" / "frostbite-guest.exe",
            base / "release" / "guest.exe",
            base / "debug" / "frostbite-guest.exe",
            base / "debug" / "guest.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _run_upload_guest(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._show_result("[#ffaa00]No accounts file. Run Accounts -> Init/Create first.[/]")
            return

        guest_value = self.query_one("#models-guest-path", Input).value.strip()
        if not guest_value:
            guessed = self._guess_guest_binary_path(proj.manifest_path)
            if not guessed:
                self._show_result("[#ff3366]Enter guest ELF path[/]")
                return
            guest_path = guessed
            try:
                display_path = str(guessed.relative_to(proj.path))
            except Exception:
                display_path = str(guessed)
            self.query_one("#models-guest-path", Input).value = display_path
        else:
            guest_path = Path(guest_value).expanduser()
            if not guest_path.is_absolute():
                guest_path = proj.manifest_path.parent / guest_path

        if not guest_path.exists():
            self._show_result(f"[#ff3366]Guest ELF not found: {guest_path}[/]")
            return

        self._show_result(f"[#ffaa00]Uploading guest program: {guest_path.name}...[/]")
        self._log_info(f"Uploading guest program: {guest_path.name}")
        runtime = resolve_runtime_context(proj)
        result = cmd_program_load(
            program_path=guest_path,
            accounts_path=proj.accounts_path,
            rpc_url=runtime.rpc_url,
            payer=runtime.payer,
            program_id=runtime.program_id,
        )
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            for line in result.logs:
                lines.append(f"  [#8892a4]{line}[/]")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
            self._hide_upload_form()
        else:
            lines = [f"[#ff3366]{result.message}[/]"]
            for line in result.logs:
                lines.append(f"  [#8892a4]{line}[/]")
            self._show_result("\n".join(lines))
            self._log_error(result.message)

    def _run_validate(self, manifest) -> None:
        result = cmd_validate(manifest)
        if result.success:
            self._show_result(f"[#39ff14]{result.message}[/]")
            self._log_success(result.message)
        else:
            lines = [f"[#ff3366]{result.message}[/]"]
            for e in result.errors:
                lines.append(f"  [#ff3366]-[/] {e}")
            self._show_result("\n".join(lines))
            self._log_error(result.message)
            for e in result.errors:
                self._log_error(f"  {e}")

    def _run_show(self, manifest) -> None:
        result = cmd_show(manifest)
        if result.success:
            manifest_data = result.data.get("manifest", {})
            lines: list[str] = []
            for section in ("model", "schema", "abi", "weights", "limits"):
                data = manifest_data.get(section)
                if not data:
                    continue
                lines.append(f"[#00ffcc][{section}][/]")
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            lines.append(f"  [#8892a4]{k}:[/]")
                            for dk, dv in v.items():
                                lines.append(f"    [#555e6e]{dk}:[/] {dv}")
                        elif isinstance(v, list):
                            lines.append(f"  [#8892a4]{k}:[/]")
                            for i, item in enumerate(v):
                                if isinstance(item, dict):
                                    lines.append(f"    [#555e6e]({i})[/]")
                                    for ik, iv in item.items():
                                        lines.append(f"      [#555e6e]{ik}:[/] {iv}")
                                else:
                                    lines.append(f"    {item}")
                        else:
                            lines.append(f"  [#8892a4]{k}:[/] {v}")
                lines.append("")
            self._show_result("\n".join(lines) if lines else "Empty manifest")
            self._log_success("Manifest displayed")
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_build_guest(self, manifest) -> None:
        self._show_result("[#ffaa00]Building guest...[/]")
        self._log_info("Starting guest build...")
        result = cmd_build_guest(manifest)
        if result.success:
            guest_dir = result.data.get("guest_dir", "?")
            target = result.data.get("target", "?")
            lines = [
                f"[#39ff14]{result.message}[/]",
                f"  [#8892a4]guest_dir:[/] {guest_dir}",
                f"  [#8892a4]target:[/] {target}",
            ]
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_schema_hash(self, manifest) -> None:
        result = cmd_schema_hash(manifest)
        if result.success:
            h = result.data.get("hash", "?")
            lines = [
                f"[#39ff14]{result.message}[/]",
                f"  [#8892a4]hash:[/] [#00ffcc]{h}[/]",
            ]
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _show_result(self, text: str) -> None:
        try:
            self.query_one("#models-result", Static).update(text)
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
