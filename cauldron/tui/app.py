"""CauldronApp — main Textual application."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.command import Hit, Hits, Provider

from .state import AppState


class CauldronCommandProvider(Provider):
    """Provides fuzzy-searchable commands for the command palette."""

    async def search(self, query: str) -> Hits:
        commands = [
            ("Validate Manifest", "cmd_validate"),
            ("Show Manifest", "cmd_show"),
            ("Pack Manifest", "cmd_pack"),
            ("Build Guest", "cmd_build_guest"),
            ("Schema Hash", "cmd_schema_hash"),
            ("Chunk Weights", "cmd_chunk"),
            ("Show Accounts", "cmd_accounts_show"),
            ("Init Accounts", "cmd_accounts_init"),
            ("Read Output", "cmd_output"),
            ("New Project", "action_new_project"),
            ("Go Home", "action_home"),
            ("Settings", "action_settings"),
            ("Wizard Mode", "action_wizard"),
            ("Copy Agent Context", "action_copy_context"),
            ("Quit Cauldron", "action_quit_app"),
        ]
        for name, action in commands:
            if query.lower() in name.lower():
                yield Hit(
                    1.0 - (len(query) / len(name)) if query else 0.0,
                    name,
                    self._run_command(action),
                    help=f"Run {name}",
                )

    def _run_command(self, action: str):  # noqa: ANN202
        async def callback() -> None:
            if hasattr(self.app, action):
                method = getattr(self.app, action)
                method()
        return callback


class CauldronApp(App):
    """Cauldron TUI — on-chain AI model deployment."""

    CSS_PATH = "theme.tcss"
    TITLE = "CAULDRON"
    SUB_TITLE = "on-chain AI"

    COMMANDS = {CauldronCommandProvider}

    BINDINGS = [
        Binding("ctrl+p", "command_palette", "Command Palette", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit_app", "Quit", show=False),
        Binding("f10", "quit_app", "Quit", show=False),
        Binding("ctrl+h", "home", "Home", show=True),
        Binding("ctrl+y", "copy_context", "Copy Context", show=True),
        Binding("ctrl+s", "settings", "Settings", show=False),
        Binding("escape", "back", "Back", show=False),
    ]

    def __init__(self, project_path: Path | None = None) -> None:
        super().__init__()
        self.app_state = AppState(project_path=project_path)

    def on_mount(self) -> None:
        from .screens.home import HomeScreen

        self.push_screen(HomeScreen())

    def _is_home_screen(self) -> bool:
        try:
            from .screens.home import HomeScreen

            return isinstance(self.screen, HomeScreen)
        except Exception:
            return self.screen.__class__.__name__ == "HomeScreen"

    def action_home(self) -> None:
        from .screens.home import HomeScreen

        if self._is_home_screen():
            return
        while len(self.screen_stack) > 1 and not self._is_home_screen():
            self.pop_screen()
        if not self._is_home_screen():
            self.push_screen(HomeScreen())

    def action_back(self) -> None:
        if self._is_home_screen():
            return
        if len(self.screen_stack) > 1:
            self.pop_screen()
        if not self._is_home_screen():
            self.action_home()

    def action_quit_app(self) -> None:
        self.exit()

    def action_new_project(self) -> None:
        from .screens.project_setup import ProjectSetupScreen

        self.push_screen(ProjectSetupScreen())

    def action_settings(self) -> None:
        from .screens.settings import SettingsScreen

        self.push_screen(SettingsScreen())

    def action_copy_context(self) -> None:
        from .agent_context import (
            copy_text_to_clipboard,
            render_agent_context,
            write_agent_context,
        )

        active_project = self.app_state.active_project
        if not active_project:
            self.notify("No active project", severity="warning")
            return

        screen = self.screen
        if hasattr(screen, "action_copy_context"):
            try:
                getattr(screen, "action_copy_context")()
                return
            except Exception:
                pass

        payload = {
            "source": type(screen).__name__.lower(),
            "logs": [],
            "last_error": None,
        }
        if hasattr(screen, "export_agent_context_payload"):
            try:
                exported = getattr(screen, "export_agent_context_payload")()
                if isinstance(exported, dict):
                    payload.update(exported)
            except Exception:
                pass

        context_text = render_agent_context(project=active_project, **payload)
        out_path = write_agent_context(active_project.path, context_text)
        copied, tool_msg = copy_text_to_clipboard(context_text)
        if copied:
            self.notify(f"Agent context saved and copied ({tool_msg})", severity="information")
        else:
            self.notify(f"Agent context saved ({tool_msg})", severity="warning")

    # ── Command wrappers for palette ──────────────────────────────

    def cmd_validate(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_validate

        result = cmd_validate(proj.manifest_path)
        if result.success:
            self.notify(result.message, severity="information")
        else:
            self.notify(result.message, severity="error")

    def cmd_show(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_show

        result = cmd_show(proj.manifest_path)
        if result.success:
            self.notify("Manifest loaded — see Models panel", severity="information")
        else:
            self.notify(result.message, severity="error")

    def cmd_pack(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_pack

        result = cmd_pack(proj.manifest_path, update_size=True)
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_build_guest(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_build_guest

        result = cmd_build_guest(proj.manifest_path)
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_schema_hash(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_schema_hash

        result = cmd_schema_hash(proj.manifest_path)
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_chunk(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_chunk

        result = cmd_chunk(manifest_path=proj.manifest_path)
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_accounts_show(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        if not proj.accounts_path or not proj.accounts_path.exists():
            self.notify("No accounts file found", severity="warning")
            return
        from .commands import cmd_accounts_show

        result = cmd_accounts_show(proj.accounts_path)
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_output(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        if not proj.accounts_path or not proj.accounts_path.exists():
            self.notify("No accounts file found", severity="warning")
            return
        from .commands import cmd_output

        result = cmd_output(
            manifest_path=proj.manifest_path,
            accounts_path=proj.accounts_path,
        )
        self.notify(result.message, severity="information" if result.success else "error")

    def cmd_accounts_init(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("No active project", severity="warning")
            return
        from .commands import cmd_accounts_init

        result = cmd_accounts_init(manifest_path=proj.manifest_path)
        self.notify(result.message, severity="information" if result.success else "error")

    def action_wizard(self) -> None:
        proj = self.app_state.active_project
        if not proj:
            self.notify("Select a project first", severity="warning")
            return
        from .screens.wizard import WizardScreen

        self.push_screen(WizardScreen(project=proj))
