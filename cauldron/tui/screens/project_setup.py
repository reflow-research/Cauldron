"""ProjectSetupScreen — create a new model project."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Input, Select, Static

from ..commands import TEMPLATES, cmd_init
from ..registry import register_project
from ..runtime import resolve_runtime_context
from ..state import ProjectInfo
from ..widgets.header import CauldronHeader
from ..widgets.status_bar import StatusBar


class ProjectSetupScreen(Screen):
    """Form for creating a new Cauldron project."""

    BINDINGS = [
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield CauldronHeader()
        with Vertical(id="setup-form"):
            yield Static("[#00ffcc]New Project[/]", classes="panel-title")
            yield Static("")
            yield Static("[#8892a4]Template[/]", classes="input-label")
            yield Select(
                [(t, t) for t in TEMPLATES],
                value="linear",
                id="select-template",
            )
            yield Static("")
            yield Static("[#8892a4]Project directory[/]", classes="input-label")
            yield Input(
                placeholder="./my-model",
                id="input-path",
            )
            yield Static("")
            yield Static("[#8892a4]Manifest filename[/]", classes="input-label")
            yield Input(
                value="frostbite-model.toml",
                id="input-manifest",
            )
            yield Static("")
            yield Checkbox(
                "Allow non-empty directory (only if no Cauldron files would be overwritten)",
                id="setup-allow-non-empty",
                value=False,
            )
            yield Static("")
            with Vertical(id="setup-buttons"):
                yield Button("Create Project", id="btn-create", variant="primary")
                yield Button("Cancel", id="btn-cancel")
            yield Static("", id="setup-status")
        yield StatusBar()
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            await self._create_project()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    async def _create_project(self) -> None:
        template_select = self.query_one("#select-template", Select)
        path_input = self.query_one("#input-path", Input)
        manifest_input = self.query_one("#input-manifest", Input)

        template = str(template_select.value) if template_select.value != Select.BLANK else "linear"
        raw_path = path_input.value.strip()
        manifest_name = manifest_input.value.strip() or "frostbite-model.toml"
        allow_non_empty = self.query_one("#setup-allow-non-empty", Checkbox).value

        if not raw_path:
            self.notify("Please enter a project directory", severity="error")
            return

        project_path = Path(raw_path).expanduser().resolve()
        status = self.query_one("#setup-status", Static)

        if project_path.exists() and any(project_path.iterdir()):
            conflicts = self._find_conflicts(project_path, manifest_name)
            if not allow_non_empty:
                status.update(
                    f"[#ff3366]Error: Destination not empty: {project_path}[/]\n"
                    "[#8892a4]Enable the non-empty directory option to allow safe initialization.[/]"
                )
                self.notify("Destination directory is not empty", severity="error")
                return
            if conflicts:
                status.update(
                    "[#ff3366]Error: Destination has conflicting Cauldron files:[/]\n"
                    + "\n".join(f"[#ff3366]- {item}[/]" for item in conflicts)
                )
                self.notify("Destination has conflicting Cauldron files", severity="error")
                return

        status.update("[#ffaa00]Creating project...[/]")

        result = cmd_init(
            path=project_path,
            template=template,
            manifest_name=manifest_name,
            allow_non_empty=allow_non_empty,
        )

        if result.success:
            project = ProjectInfo(
                name=project_path.name,
                path=project_path,
                manifest_path=project_path / manifest_name,
                template=template,
                deployment_state="init",
            )
            runtime = resolve_runtime_context(project)
            project.cluster = runtime.cluster
            project.rpc_url = runtime.rpc_url
            project.program_id = runtime.program_id
            project.payer = runtime.payer
            register_project(project)
            self.app.app_state.set_active_project(project)  # type: ignore[attr-defined]
            self.notify(f"Created {template} project: {project_path.name}", severity="information")
            self.app.pop_screen()
            await self._open_created_project(project)
        else:
            status.update(f"[#ff3366]Error: {result.message}[/]")

    def _find_conflicts(self, project_path: Path, manifest_name: str) -> list[str]:
        conflicts: list[str] = []
        if (project_path / manifest_name).exists():
            conflicts.append(manifest_name)
        if (project_path / "guest").exists():
            conflicts.append("guest/")
        return conflicts

    async def _open_created_project(self, project: ProjectInfo) -> None:
        """After successful creation, refresh home and open mode picker for the new project."""
        from .home import HomeScreen, ModePickerScreen

        screen = self.app.screen
        if isinstance(screen, HomeScreen):
            await screen._load_projects()
            screen._update_chrome(project)
            screen._show_mode_picker(project)
            return
        self.app.push_screen(ModePickerScreen(project))
