"""AccountsPanel — account lifecycle management."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from ..commands import cmd_accounts_show, cmd_accounts_init, cmd_accounts_create, cmd_accounts_close_vm
from ..widgets.command_list import CommandItem, CommandList


_COMMANDS = [
    CommandItem("Show Accounts", "show", "Display account mapping and PDAs"),
    CommandItem("Init Accounts", "init", "Generate accounts configuration"),
    CommandItem("Create Accounts", "create", "Allocate accounts on-chain"),
    CommandItem("Close VM", "close-vm", "Close VM PDA and drain lamports"),
]


class AccountsPanel(Widget):
    """Panel for Solana account management."""

    DEFAULT_CSS = """
    AccountsPanel {
        height: 1fr;
    }
    AccountsPanel #accounts-result-scroll {
        height: 1fr;
        min-height: 4;
        background: #0a0e17;
        border: solid #1a3a4a;
        margin-top: 1;
        padding: 0 1;
    }
    AccountsPanel #accounts-init-form {
        height: auto;
        padding: 1 0;
        display: none;
    }
    AccountsPanel #accounts-init-form.-visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(classes="panel"):
            yield Static("[#00ffcc bold]ACCOUNTS[/]", classes="panel-title")
            yield CommandList(_COMMANDS, id="accounts-commands")

            # Init form (hidden by default)
            with Vertical(id="accounts-init-form"):
                yield Static("[#8892a4]RAM segments (1-14)[/]", classes="input-label")
                yield Input(value="1", id="accounts-ram-count")
                yield Static("[#8892a4]RAM bytes per segment[/]", classes="input-label")
                yield Input(value="262144", id="accounts-ram-bytes")
                with Horizontal(classes="form-row"):
                    yield Button("Create Config", id="btn-accounts-init", variant="primary")
                    yield Button("Cancel", id="btn-accounts-init-cancel")

            with VerticalScroll(id="accounts-result-scroll"):
                yield Static("", id="accounts-result")

    def on_command_list_selected(self, event: CommandList.Selected) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        if event.key == "show":
            self._run_show(proj)
        elif event.key == "init":
            self._show_init_form()
        elif event.key == "create":
            self._run_create(proj)
        elif event.key == "close-vm":
            self._run_close_vm(proj)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-accounts-init":
            self._run_init()
        elif event.button.id == "btn-accounts-init-cancel":
            self._hide_init_form()

    def _show_init_form(self) -> None:
        try:
            self.query_one("#accounts-init-form").add_class("-visible")
        except Exception:
            pass

    def _hide_init_form(self) -> None:
        try:
            self.query_one("#accounts-init-form").remove_class("-visible")
        except Exception:
            pass

    def _run_init(self) -> None:
        app_state = self.app.app_state  # type: ignore[attr-defined]
        proj = app_state.active_project
        if not proj:
            self._show_result("[#ff3366]No active project[/]")
            return

        try:
            ram_count = int(self.query_one("#accounts-ram-count", Input).value.strip() or "1")
            ram_bytes = int(self.query_one("#accounts-ram-bytes", Input).value.strip() or "262144")
        except ValueError:
            self._show_result("[#ff3366]Invalid number[/]")
            return

        self._show_result("[#ffaa00]Generating accounts...[/]")
        self._log_info("Initializing accounts config...")

        result = cmd_accounts_init(
            manifest_path=proj.manifest_path,
            ram_count=ram_count,
            ram_bytes=ram_bytes,
        )
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            seed = result.data.get("vm_seed")
            if seed is not None:
                lines.append(f"  [#8892a4]vm_seed:[/] {seed}")
            path = result.data.get("path")
            if path:
                lines.append(f"  [#8892a4]file:[/] {path}")
                # Update project accounts path
                proj.accounts_path = Path(path)
            self._show_result("\n".join(lines))
            self._log_success(result.message)
            self._hide_init_form()
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_show(self, proj) -> None:
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._show_result("[#ffaa00]No accounts file found. Run 'Init Accounts' first.[/]")
            return
        result = cmd_accounts_show(proj.accounts_path)
        if result.success:
            info = result.data.get("info", {})
            mapped = result.data.get("mapped", [])
            lines = ["[#00ffcc]Account Mapping[/]"]
            for k, v in info.items():
                if v is not None:
                    lines.append(f"  [#8892a4]{k}:[/] {v}")
            if mapped:
                lines.append("")
                lines.append("[#00ffcc]Segments[/]")
                for i, m in enumerate(mapped):
                    lines.append(f"  [#555e6e]seg {i + 1}:[/] {m}")
            self._show_result("\n".join(lines))
            self._log_success("Accounts loaded")
        else:
            self._show_result(f"[#ff3366]{result.message}[/]")
            self._log_error(result.message)

    def _run_create(self, proj) -> None:
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._show_result("[#ffaa00]No accounts file. Run 'Init Accounts' first.[/]")
            return

        self._show_result("[#ffaa00]Creating accounts on-chain...[/]")
        self._log_info("Creating PDA accounts...")

        result = cmd_accounts_create(accounts_path=proj.accounts_path)
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            for log_line in result.logs:
                lines.append(f"  [#8892a4]{log_line}[/]")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            lines = [f"[#ff3366]{result.message}[/]"]
            for log_line in result.logs:
                lines.append(f"  [#8892a4]{log_line}[/]")
            self._show_result("\n".join(lines))
            self._log_error(result.message)

    def _run_close_vm(self, proj) -> None:
        if not proj.accounts_path or not proj.accounts_path.exists():
            self._show_result("[#ffaa00]No accounts file.[/]")
            return

        self._show_result("[#ffaa00]Closing VM...[/]")
        self._log_info("Closing VM PDA...")

        result = cmd_accounts_close_vm(accounts_path=proj.accounts_path)
        if result.success:
            lines = [f"[#39ff14]{result.message}[/]"]
            for log_line in result.logs:
                lines.append(f"  [#8892a4]{log_line}[/]")
            self._show_result("\n".join(lines))
            self._log_success(result.message)
        else:
            lines = [f"[#ff3366]{result.message}[/]"]
            for log_line in result.logs:
                lines.append(f"  [#8892a4]{log_line}[/]")
            self._show_result("\n".join(lines))
            self._log_error(result.message)

    def _show_result(self, text: str) -> None:
        try:
            self.query_one("#accounts-result", Static).update(text)
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
