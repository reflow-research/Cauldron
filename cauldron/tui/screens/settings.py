"""SettingsScreen — global configuration for cluster, RPC, payer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Select, Static

from ..registry import get_defaults, load_registry, save_registry, set_defaults
from ..widgets.header import CauldronHeader
from ..widgets.status_bar import StatusBar


_CLUSTERS = [
    ("devnet", "devnet"),
    ("mainnet", "mainnet"),
    ("localnet", "localnet"),
]


class SettingsScreen(Screen):
    """Global settings: cluster, RPC URL, payer keypair, program ID."""

    BINDINGS = [
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield CauldronHeader()
        with Vertical(id="settings-form"):
            yield Static("[#00ffcc bold]SETTINGS[/]", classes="panel-title")
            yield Static("")

            yield Static("[#ff00aa bold]Cluster[/]", classes="group-title")
            yield Static("[#8892a4]Default cluster[/]", classes="input-label")
            yield Select(
                _CLUSTERS,
                value="devnet",
                id="settings-cluster",
            )

            yield Static("")
            yield Static("[#8892a4]RPC URL (leave blank for default)[/]", classes="input-label")
            yield Input(placeholder="https://api.devnet.solana.com", id="settings-rpc")

            yield Static("")
            yield Static("[#8892a4]Payer keypair path[/]", classes="input-label")
            yield Input(placeholder="~/.config/solana/id.json", id="settings-payer")

            yield Static("")
            yield Static("[#8892a4]Program ID[/]", classes="input-label")
            yield Input(placeholder="default", id="settings-program-id")

            yield Static("")
            with Vertical(id="settings-buttons"):
                yield Button("Save", id="btn-settings-save", variant="primary")
                yield Button("Cancel", id="btn-settings-cancel")

            yield Static("", id="settings-status")

        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        defaults = get_defaults()
        try:
            cluster = defaults.get("default_cluster", "devnet")
            self.query_one("#settings-cluster", Select).value = cluster
        except Exception:
            pass
        rpc = defaults.get("default_rpc_url", "")
        if rpc:
            self.query_one("#settings-rpc", Input).value = rpc
        payer = defaults.get("default_payer", "")
        if payer:
            self.query_one("#settings-payer", Input).value = payer
        pid = defaults.get("default_program_id", "")
        if pid:
            self.query_one("#settings-program-id", Input).value = pid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-settings-save":
            self._save()
        elif event.button.id == "btn-settings-cancel":
            self.app.pop_screen()

    def _save(self) -> None:
        cluster_select = self.query_one("#settings-cluster", Select)
        cluster = str(cluster_select.value) if cluster_select.value != Select.BLANK else "devnet"
        rpc = self.query_one("#settings-rpc", Input).value.strip()
        payer = self.query_one("#settings-payer", Input).value.strip()
        pid = self.query_one("#settings-program-id", Input).value.strip()

        set_defaults(
            cluster=cluster,
            rpc_url=rpc or None,
            payer=payer or None,
            program_id=pid or None,
        )

        status = self.query_one("#settings-status", Static)
        status.update("[#39ff14]Settings saved[/]")
        self.notify("Settings saved", severity="information")
