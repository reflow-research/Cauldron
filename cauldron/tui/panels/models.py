"""ModelsPanel — validate, show, build-guest, schema-hash."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from ..commands import cmd_validate, cmd_show, cmd_schema_hash, cmd_build_guest
from ..widgets.command_list import CommandItem, CommandList


_COMMANDS = [
    CommandItem("Validate Manifest", "validate", "Check manifest against spec"),
    CommandItem("Show Manifest", "show", "Display manifest sections"),
    CommandItem("Build Guest", "build-guest", "Compile RISC-V guest program"),
    CommandItem("Schema Hash", "schema-hash", "Compute schema hash"),
]


class ModelsPanel(Widget):
    """Panel for model lifecycle actions."""

    DEFAULT_CSS = """
    ModelsPanel {
        height: 1fr;
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
            self._run_validate(manifest)
        elif event.key == "show":
            self._run_show(manifest)
        elif event.key == "build-guest":
            self._run_build_guest(manifest)
        elif event.key == "schema-hash":
            self._run_schema_hash(manifest)

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
