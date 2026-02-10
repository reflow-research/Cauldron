"""BubblingCauldron — animated ASCII art cauldron for the home screen."""

from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


_BUBBLE_FRAMES = [
    [
        "[#00ffcc]      °    .       ○     .    °[/]",
        "[#00ffcc dim]         .    °    ○       °[/]",
        "[#00ffcc]       ○  .    °       .   ○[/]",
    ],
    [
        "[#00ffcc dim]        .  ○     °    .     °[/]",
        "[#00ffcc]      °       .    ○    .    ○[/]",
        "[#00ffcc]         ○     °       °  .  [/]",
    ],
    [
        "[#00ffcc]       ○    °    .      °    .[/]",
        "[#00ffcc]          °    .    ○  .   ○  [/]",
        "[#00ffcc dim]      .       ○       .  °  [/]",
    ],
    [
        "[#00ffcc]         .     °    ○     .   °[/]",
        "[#00ffcc dim]      ○    .       .    °    [/]",
        "[#00ffcc]        °    ○    .      ○   [/]",
    ],
]

# ── Cauldron parts (platformer side view, centered on 40-char canvas) ──

_RIM = f"[#555e6e]        ▄▄[/][#8892a4]{'▄' * 20}[/][#555e6e]▄▄[/]"

# Single thin liquid line — just barely visible at the rim (side view)
_LIQUID_A = [
    f"[#8892a4]        █[/][#00ffcc]{'░▒' * 11}[/][#8892a4]█[/]",
]

_LIQUID_B = [
    f"[#8892a4]        █[/][#00ffcc]{'▒░' * 11}[/][#8892a4]█[/]",
]

_BODY = [
    # Rim lip — solid flare wider than opening
    f"[#8892a4]     ▄{'█' * 28}▄[/]",
    # Wireframe transition — green drips start
    f"[#8892a4]  ██[/][#00ffcc]░[/]{' ' * 30}[#00ffcc]░[/][#8892a4]██[/]",
    # Handle line — green drips continue
    f" [#8892a4]▐██[/][#00ffcc]░[/]{' ' * 30}[#00ffcc]░[/][#8892a4]██▌[/]",
    # Body — drips fading
    f"[#8892a4]██[/][#00ffcc]░[/]{' ' * 34}[#00ffcc]░[/][#8892a4]██[/]",
    f"[#8892a4]██[/][#00ffcc dim]░[/]{' ' * 34}[#00ffcc dim]░[/][#8892a4]██[/]",
    # Body — clean middle
    f"[#8892a4]██[/]{' ' * 36}[#8892a4]██[/]",
    # Taper — heat glow building from the fire
    f"[#8892a4]  ██[/][#ffaa00 dim]░[/]{' ' * 30}[#ffaa00 dim]░[/][#8892a4]██[/]",
    f"[#555e6e]    ██[/][#ffaa00]░[/]{' ' * 26}[#ffaa00]░[/][#555e6e]██[/]",
    f"[#555e6e]      ██[/][#ffaa00]░▒[/]{' ' * 20}[#ffaa00]▒░[/][#555e6e]██[/]",
    # Bottom — solid to close the shape
    f"[#555e6e]       {'█' * 26}[/]",
]

# ── Smoldering fire frames (subtle flicker) ──

_FIRE_FRAMES = [
    f"[#555e6e]      ████[/] [#ffaa00]░▒░▒░[/] [#ff3366]░▒░▒░▒[/] [#ffaa00]░▒░▒░[/] [#555e6e]████[/]",
    f"[#555e6e]      ████[/] [#ffaa00]▒░▒░▒[/] [#ff3366]▒░▒░▒░[/] [#ffaa00]▒░▒░▒[/] [#555e6e]████[/]",
    f"[#555e6e]      ████[/] [#ff3366]░▒░▒░[/] [#ffaa00]░▒░▒░▒[/] [#ff3366]░▒░▒░[/] [#555e6e]████[/]",
    f"[#555e6e]      ████[/] [#ff3366]▒░▒░▒[/] [#ffaa00]▒░▒░▒░[/] [#ff3366]▒░▒░▒[/] [#555e6e]████[/]",
]


class BubblingCauldron(Static):
    """Animated ASCII art cauldron with bubbling potion."""

    DEFAULT_CSS = """
    BubblingCauldron {
        width: 44;
        height: 1fr;
        content-align: center bottom;
    }
    """

    _frame: reactive[int] = reactive(0)

    def on_mount(self) -> None:
        self.update(self._build_art(0))
        self.set_interval(0.5, self._next_frame)

    def _next_frame(self) -> None:
        self._frame = (self._frame + 1) % len(_BUBBLE_FRAMES)

    def watch__frame(self, value: int) -> None:
        self.update(self._build_art(value))

    def _build_art(self, frame: int) -> str:
        bubbles = _BUBBLE_FRAMES[frame]
        liquid = _LIQUID_A if frame % 2 == 0 else _LIQUID_B
        fire = _FIRE_FRAMES[frame % len(_FIRE_FRAMES)]
        lines = bubbles + [_RIM] + liquid + _BODY + [fire]
        return "\n".join(lines)
