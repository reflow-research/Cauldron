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

# ── Cauldron parts (all lines centered at position 19.5 on a 40-char canvas) ──

_RIM = f"[#555e6e]     ▄▄[/][#8892a4]{'█' * 26}[/][#555e6e]▄▄[/]"

_LIQUID_A = [
    f"[#8892a4]    ██[/][#00ffcc]{'░▒' * 14}[/][#8892a4]██[/]",
    f"[#8892a4]  ▄██[/][#00ffcc]{'░▒' * 15}[/][#8892a4]██▄[/]",
]

_LIQUID_B = [
    f"[#8892a4]    ██[/][#00ffcc]{'▒░' * 14}[/][#8892a4]██[/]",
    f"[#8892a4]  ▄██[/][#00ffcc]{'▒░' * 15}[/][#8892a4]██▄[/]",
]

_BODY = [
    # Handles — 30 inner blocks
    f" [#8892a4]▐██ {'█' * 30} ██▌[/]",
    f" [#8892a4]▐██ {'█' * 30} ██▌[/]",
    # Widest body — 40 blocks
    f"[#8892a4]{'█' * 40}[/]",
    f"[#8892a4]{'█' * 40}[/]",
    f"[#8892a4]{'█' * 40}[/]",
    f"[#8892a4]{'█' * 40}[/]",
    # Taper — symmetric narrowing
    f"[#8892a4]  {'█' * 36}[/]",
    f"[#8892a4]   {'█' * 34}[/]",
    f"[#555e6e]    {'█' * 32}[/]",
    f"[#555e6e]      {'█' * 28}[/]",
    f"[#555e6e]       {'█' * 26}[/]",
    # Stubby feet + fire combined on one line — no gap
    f"[#555e6e]      ████[/] [#ffaa00]░▒░▒░[/] [#ff3366]░▒░▒░▒[/] [#ffaa00]░▒░▒░[/] [#555e6e]████[/]",
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
        lines = bubbles + [_RIM] + liquid + _BODY
        return "\n".join(lines)
