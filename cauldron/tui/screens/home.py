"""HomeScreen — project list, mode selector, and entry point."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from ..registry import discover_project, list_projects, register_project
from ..state import ProjectInfo
from ..widgets.cauldron_art import BubblingCauldron
from ..widgets.header import CauldronHeader
from ..widgets.project_card import ProjectCard
from ..widgets.status_bar import StatusBar


_WELCOME_ART = r"""[#00ffcc]
  ██████╗ █████╗ ██╗   ██╗██╗     ██████╗ ██████╗  ██████╗ ███╗   ██╗
 ██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗██╔══██╗██╔═══██╗████╗  ██║
 ██║     ███████║██║   ██║██║     ██║  ██║██████╔╝██║   ██║██╔██╗ ██║
 ██║     ██╔══██║██║   ██║██║     ██║  ██║██╔══██╗██║   ██║██║╚██╗██║
 ╚██████╗██║  ██║╚██████╔╝███████╗██████╔╝██║  ██║╚██████╔╝██║ ╚████║
  ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═══╝[/]
[#8892a4]AI inference on Solana[/]
"""

_DIVIDER = (
    "[#1a3a4a]────────────────[/]"
    "[#555e6e]═══╣[/] "
    "[#00ffcc]◆[/]"
    " [#555e6e]╠═══[/]"
    "[#1a3a4a]────────────────[/]"
)


class HomeScreen(Screen):
    """Main landing screen — shows projects and mode selection."""

    BINDINGS = [
        Binding("n", "new_project", "New Project"),
        Binding("i", "import_project", "Import"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "settings", "Settings"),
        Binding("q", "quit_app", "Quit"),
        Binding("left", "prev_card", "Prev", show=False, priority=True),
        Binding("right", "next_card", "Next", show=False, priority=True),
        Binding("up", "nav_up", "Up", show=False, priority=True),
        Binding("down", "nav_down", "Down", show=False, priority=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._projects: list[ProjectInfo] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        yield CauldronHeader()
        with Vertical(id="home-main"):
            yield Static(_WELCOME_ART, id="home-welcome")
            with Horizontal(id="home-content"):
                with Vertical(id="home-carousel-area"):
                    with Vertical(id="carousel-wrapper"):
                        yield Static(
                            "[#8892a4]Select a project to begin, or create a new one.[/]",
                            id="home-hint",
                        )
                        with Horizontal(id="card-carousel"):
                            yield Static(
                                "[#555e6e dim]◀[/]",
                                id="carousel-prev",
                                classes="carousel-arrow",
                            )
                            yield Container(id="card-display")
                            yield Static(
                                "[#555e6e dim]▶[/]",
                                id="carousel-next",
                                classes="carousel-arrow",
                            )
                        yield Static("", id="carousel-indicator")
                yield BubblingCauldron(id="home-cauldron")
            yield Static(_DIVIDER, id="home-divider")
            with Horizontal(id="home-actions"):
                yield Button("New Project", id="btn-new", variant="primary")
                yield Button("Import Existing", id="btn-import")
                yield Button("Settings", id="btn-settings")
                yield Button("Refresh", id="btn-refresh")
        yield StatusBar()
        yield Footer()

    async def on_mount(self) -> None:
        await self._load_projects()
        app_state = self.app.app_state  # type: ignore[attr-defined]
        if app_state._initial_project_path:
            proj = discover_project(app_state._initial_project_path)
            if proj:
                register_project(proj)
                await self._load_projects()
        elif not app_state.projects:
            cwd_proj = discover_project(Path.cwd())
            if cwd_proj:
                register_project(cwd_proj)
                await self._load_projects()
        self.call_after_refresh(self._focus_default_target)

    async def _load_projects(self) -> None:
        projects = list_projects()
        self.app.app_state.projects = projects  # type: ignore[attr-defined]
        self._projects = projects
        self._selected_index = 0
        await self._show_current_card()

    async def _show_current_card(self) -> None:
        display = self.query_one("#card-display", Container)
        await display.remove_children()

        if not self._projects:
            await display.mount(
                Static(
                    "[#8892a4]No projects yet. Create or import one to get started.[/]",
                )
            )
            self._update_indicator()
            self._update_arrows()
            return

        idx = self._selected_index
        card = ProjectCard(self._projects[idx])
        await display.mount(card)
        card.focus()
        self._update_indicator()
        self._update_arrows()

    def _update_indicator(self) -> None:
        try:
            indicator = self.query_one("#carousel-indicator", Static)
        except Exception:
            return
        if not self._projects:
            indicator.update("")
            return
        dots = []
        for i in range(len(self._projects)):
            if i == self._selected_index:
                dots.append("[#00ffcc]●[/]")
            else:
                dots.append("[#555e6e]○[/]")
        indicator.update("  ".join(dots))

    def _update_arrows(self) -> None:
        try:
            prev_arrow = self.query_one("#carousel-prev", Static)
            next_arrow = self.query_one("#carousel-next", Static)
        except Exception:
            return
        if self._selected_index > 0:
            prev_arrow.update("[#00ffcc]◀[/]")
        else:
            prev_arrow.update("[#555e6e dim]◀[/]")
        if self._projects and self._selected_index < len(self._projects) - 1:
            next_arrow.update("[#00ffcc]▶[/]")
        else:
            next_arrow.update("[#555e6e dim]▶[/]")

    def on_project_card_selected(self, event: ProjectCard.Selected) -> None:
        self.app.app_state.set_active_project(event.project)  # type: ignore[attr-defined]
        self._update_chrome(event.project)
        self._show_mode_picker(event.project)

    def _update_chrome(self, project: ProjectInfo) -> None:
        try:
            header = self.query_one(CauldronHeader)
            header.project_name = project.name
            header.cluster_name = project.cluster or "devnet"
        except Exception:
            pass
        try:
            sb = self.query_one(StatusBar)
            sb.project = project.name
            sb.cluster = project.cluster or "devnet"
        except Exception:
            pass

    def _show_mode_picker(self, project: ProjectInfo) -> None:
        """Push a mode-picker modal."""
        self.app.push_screen(ModePickerScreen(project))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self.action_new_project()
        elif event.button.id == "btn-import":
            await self.action_import_project()
        elif event.button.id == "btn-refresh":
            await self.action_refresh()
        elif event.button.id == "btn-settings":
            self.action_settings()

    def action_new_project(self) -> None:
        from .project_setup import ProjectSetupScreen

        self.app.push_screen(ProjectSetupScreen())

    async def action_import_project(self) -> None:
        """Import project from current working directory."""
        proj = discover_project(Path.cwd())
        if proj:
            register_project(proj)
            await self._load_projects()
            self.notify(f"Imported: {proj.name}", severity="information")
        else:
            self.notify("No frostbite-model.toml found in current directory", severity="warning")

    async def action_refresh(self) -> None:
        await self._load_projects()

    def action_settings(self) -> None:
        from .settings import SettingsScreen

        self.app.push_screen(SettingsScreen())

    def action_quit_app(self) -> None:
        if hasattr(self.app, "action_quit_app"):
            self.app.action_quit_app()
        else:
            self.app.exit()

    async def action_prev_card(self) -> None:
        if self._projects and self._selected_index > 0:
            self._selected_index -= 1
            await self._show_current_card()

    async def action_next_card(self) -> None:
        if self._projects and self._selected_index < len(self._projects) - 1:
            self._selected_index += 1
            await self._show_current_card()

    def action_nav_up(self) -> None:
        self.focus_previous()

    def action_nav_down(self) -> None:
        self.focus_next()

    def _focus_default_target(self) -> None:
        cards = list(self.query(ProjectCard))
        if cards:
            cards[0].focus()
            return
        try:
            self.query_one("#btn-new", Button).focus()
        except Exception:
            pass


class ModePickerScreen(Screen):
    """Simple mode picker: Wizard or Manual."""

    DEFAULT_CSS = """
    ModePickerScreen {
        align: center middle;
    }
    ModePickerScreen #mode-picker-box {
        width: 60;
        height: auto;
        background: #111827;
        border: solid #00ffcc;
        padding: 2 4;
    }
    ModePickerScreen .mode-title {
        color: #00ffcc;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    ModePickerScreen .mode-project {
        color: #ff00aa;
        text-style: bold;
        text-align: center;
        margin-bottom: 2;
    }
    ModePickerScreen .mode-buttons {
        height: auto;
        align-horizontal: center;
    }
    """

    BINDINGS = [
        Binding("w", "wizard", "Wizard", show=False),
        Binding("m", "manual", "Manual", show=False),
        Binding("escape", "cancel", "Cancel"),
        Binding("up", "focus_previous", "Up", show=False, priority=True),
        Binding("down", "focus_next", "Down", show=False, priority=True),
        Binding("left", "focus_previous", "Left", show=False, priority=True),
        Binding("right", "focus_next", "Right", show=False, priority=True),
    ]

    def __init__(self, project: ProjectInfo, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project = project

    def compose(self) -> ComposeResult:
        with Container(id="mode-picker-box"):
            yield Static("[#00ffcc bold]Choose Mode[/]", classes="mode-title")
            yield Static(f"[#ff00aa]{self._project.name}[/]", classes="mode-project")
            yield Static(
                "[#8892a4]Wizard guides you step-by-step through deployment.\n"
                "Manual Mode gives full panel access to all operations.[/]",
            )
            yield Static("")
            with Horizontal(classes="mode-buttons"):
                yield Button("Wizard (W)", id="btn-mode-wizard", classes="mode-btn -wizard")
                yield Button("Manual (M)", id="btn-mode-manual", classes="mode-btn -manual")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-mode-wizard":
            self.action_wizard()
        elif event.button.id == "btn-mode-manual":
            self.action_manual()

    def on_mount(self) -> None:
        try:
            self.query_one("#btn-mode-wizard", Button).focus()
        except Exception:
            pass

    def action_wizard(self) -> None:
        from .wizard import WizardScreen

        self.app.pop_screen()
        self.app.push_screen(WizardScreen(project=self._project))

    def action_manual(self) -> None:
        from .manual import ManualScreen

        self.app.pop_screen()
        self.app.push_screen(ManualScreen())

    def action_cancel(self) -> None:
        self.app.pop_screen()
