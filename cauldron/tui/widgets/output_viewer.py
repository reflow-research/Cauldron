"""OutputViewer — structured display for inference output."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static


class OutputViewer(Widget):
    """Color-coded display of inference results."""

    DEFAULT_CSS = """
    OutputViewer {
        background: #0a0e17;
        border: solid #1a3a4a;
        padding: 1 2;
        height: auto;
        max-height: 20;
    }
    OutputViewer:focus {
        border: solid #00ffcc;
    }
    OutputViewer .ov-title {
        color: #00ffcc;
        text-style: bold;
        margin-bottom: 1;
    }
    OutputViewer .ov-field {
        color: #8892a4;
    }
    OutputViewer .ov-value {
        color: #e0e6f0;
    }
    OutputViewer .ov-positive {
        color: #39ff14;
    }
    OutputViewer .ov-negative {
        color: #ff00aa;
    }
    OutputViewer .ov-zero {
        color: #555e6e;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[#00ffcc bold]Output[/]", classes="ov-title")
            yield Static("", id="ov-content")

    def display_output(self, data: dict) -> None:
        """Render inference output from cmd_output data dict."""
        lines: list[str] = []

        for key in ("rpc_url", "vm", "status", "output_len", "output_format"):
            val = data.get(key, "?")
            lines.append(f"  [#8892a4]{key}:[/] {val}")

        output = data.get("output", [])
        if isinstance(output, list) and output:
            lines.append("")
            lines.append("  [#00ffcc]values:[/]")
            formatted = []
            for v in output:
                if isinstance(v, (int, float)):
                    if v > 0:
                        formatted.append(f"[#39ff14]{v}[/]")
                    elif v < 0:
                        formatted.append(f"[#ff00aa]{v}[/]")
                    else:
                        formatted.append(f"[#555e6e]{v}[/]")
                else:
                    formatted.append(str(v))
            # Show values in rows of 8
            for i in range(0, len(formatted), 8):
                row = "  ".join(formatted[i : i + 8])
                lines.append(f"    {row}")
        elif output:
            lines.append(f"  [#00ffcc]output:[/] {output}")

        try:
            self.query_one("#ov-content", Static).update("\n".join(lines))
        except Exception:
            pass

    def clear(self) -> None:
        try:
            self.query_one("#ov-content", Static).update("")
        except Exception:
            pass
