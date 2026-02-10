"""WizardScreen — multi-step guided deployment wizard."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from ..agent_context import copy_text_to_clipboard, render_agent_context, write_agent_context
from ..commands import (
    cmd_accounts_create,
    cmd_accounts_init,
    cmd_build_guest,
    cmd_chunk,
    cmd_input_write,
    cmd_invoke,
    cmd_output,
    cmd_pack,
    cmd_program_load,
    cmd_train,
    cmd_upload,
    cmd_validate,
)
from ...manifest import load_manifest
from ..state import ProjectInfo
from ..widgets.header import CauldronHeader
from ..widgets.log_panel import LogPanel
from ..widgets.progress_tracker import ProgressTracker

_STEPS = [
    "Setup",
    "Validate",
    "Train",
    "Convert",
    "Build Guest",
    "Accounts",
    "Upload",
    "Write Input",
    "Load Prog",
    "Invoke",
    "Output",
]

_COMPLETE_STATES = frozenset({"success", "skipped"})
_HEAVY_TEMPLATES = frozenset({"cnn1d", "tiny_cnn"})
_WORKFLOW_MODES = frozenset({"deploy_existing", "train_then_deploy"})

_TEMPLATE_CAPABILITIES: dict[str, str] = {
    "linear": "vector -> score (quantized linear)",
    "softmax": "vector -> class probabilities (linear + softmax)",
    "naive_bayes": "vector -> class probabilities (NB-style logits)",
    "mlp": "vector -> hidden -> score (1 hidden layer)",
    "mlp2": "vector -> hidden1 -> hidden2 -> score",
    "mlp3": "vector -> hidden1 -> hidden2 -> hidden3 -> score",
    "cnn1d": "time_series -> score (conv1d + pool + head)",
    "tiny_cnn": "vector/image -> score (tiny conv2d + head)",
    "two_tower": "vector split -> similarity score (dot product)",
    "tree": "vector -> score (decision tree / GBDT style)",
    "custom": "raw blob in/out scaffold (replace logic for custom model)",
}


class WizardScreen(Screen):
    """Guided deployment flow that can complete full inference end-to-end."""

    BINDINGS = [
        Binding("escape", "go_home", "Home"),
        Binding("enter", "next_step", "Next", show=False, priority=True),
        Binding("right", "next_step", "Next", show=False, priority=True),
        Binding("left", "back_step", "Back", show=False, priority=True),
        Binding("s", "skip_step", "Skip", show=False),
        Binding("w", "cycle_workflow", "Workflow", show=False),
        Binding("1", "select_workflow_deploy_existing", "Deploy Flow", show=False),
        Binding("2", "select_workflow_train_then_deploy", "Train Flow", show=False),
        Binding("c", "copy_context", "Copy Context", show=False),
        Binding("p", "open_power", "Power", show=False),
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
    ]

    def __init__(self, project: ProjectInfo | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._project = project
        self._current_step = 0
        self._workflow_mode = "deploy_existing"
        self._busy = False
        self._step_states: dict[int, str] = {i: "pending" for i in range(len(_STEPS))}
        self._step_notes: dict[int, list[str]] = {}
        self._log_history: list[str] = []
        self._last_error: str | None = None
        self._invoke_signature: str | None = None
        self._output_data: dict[str, Any] | None = None
        self._generated_input_path: Path | None = None
        self._generated_context_path: Path | None = None
        self._guest_elf_path: Path | None = None

    def compose(self) -> ComposeResult:
        header = CauldronHeader()
        if self._project:
            header.project_name = self._project.name
            header.cluster_name = self._project.cluster or "devnet"
        yield header
        yield ProgressTracker(_STEPS, id="wizard-progress")

        with VerticalScroll(id="wizard-content"):
            yield Static("", id="wizard-step-content")

        with Vertical(id="wizard-bottom"):
            with Horizontal(id="wizard-nav"):
                yield Button("Back", id="btn-wiz-back")
                yield Button("Skip", id="btn-wiz-skip")
                yield Button("Copy Context", id="btn-wiz-context")
                yield Button("Next", id="btn-wiz-next", variant="primary")
            yield LogPanel(id="wizard-log")

    def on_mount(self) -> None:
        self._restore_from_state()
        self._render_step()
        self._update_nav_buttons()
        try:
            self.query_one("#btn-wiz-next", Button).focus()
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-wiz-next":
            await self.action_next_step()
        elif event.button.id == "btn-wiz-back":
            self.action_back_step()
        elif event.button.id == "btn-wiz-skip":
            self.action_skip_step()
        elif event.button.id == "btn-wiz-context":
            self.action_copy_context()

    def _restore_from_state(self) -> None:
        try:
            wizard_state = self.app.app_state.wizard  # type: ignore[attr-defined]
        except Exception:
            return

        mode = getattr(wizard_state, "workflow_mode", "deploy_existing")
        if mode in _WORKFLOW_MODES:
            self._workflow_mode = mode

        for idx in wizard_state.steps_completed:
            if 0 <= idx < len(_STEPS):
                self._step_states[idx] = "success"

        if wizard_state.guest_built:
            self._step_states[4] = "success"
        if wizard_state.accounts_created:
            self._step_states[5] = "success"
        if wizard_state.weights_uploaded:
            self._step_states[6] = "success"
        if wizard_state.input_written:
            self._step_states[7] = "success"
        if wizard_state.program_loaded:
            self._step_states[8] = "success"
        if wizard_state.invoked:
            self._step_states[9] = "success"
        if wizard_state.output_result:
            self._step_states[10] = "success"

        if wizard_state.accounts_path and self._project and not self._project.accounts_path:
            self._project.accounts_path = wizard_state.accounts_path
        if wizard_state.input_data_path:
            self._generated_input_path = wizard_state.input_data_path
        if wizard_state.invoke_signature:
            self._invoke_signature = wizard_state.invoke_signature
        if wizard_state.output_result:
            self._output_data = wizard_state.output_result

        resumed = wizard_state.current_step
        if not isinstance(resumed, int) or resumed < 0 or resumed >= len(_STEPS):
            resumed = 0
        self._current_step = resumed
        first_incomplete = self._first_incomplete_step()
        if first_incomplete > self._current_step:
            self._current_step = first_incomplete

        self._persist_state()

    def _persist_state(self) -> None:
        try:
            wizard_state = self.app.app_state.wizard  # type: ignore[attr-defined]
        except Exception:
            return
        wizard_state.current_step = self._current_step
        wizard_state.workflow_mode = self._workflow_mode
        wizard_state.steps_completed = {
            idx for idx, status in self._step_states.items() if status == "success"
        }
        wizard_state.guest_built = self._step_states.get(4) == "success"
        if self._project:
            wizard_state.template = self._project.template
            wizard_state.manifest_path = self._project.manifest_path
            wizard_state.accounts_path = self._project.accounts_path
        wizard_state.accounts_created = self._step_states.get(5) == "success"
        wizard_state.weights_uploaded = self._step_states.get(6) == "success"
        wizard_state.input_data_path = self._generated_input_path
        wizard_state.input_written = self._step_states.get(7) == "success"
        wizard_state.program_loaded = self._step_states.get(8) == "success"
        wizard_state.invoked = self._step_states.get(9) == "success"
        wizard_state.invoke_signature = self._invoke_signature
        wizard_state.output_result = self._output_data

    def _first_incomplete_step(self) -> int:
        for idx in range(len(_STEPS)):
            if self._step_states.get(idx) not in _COMPLETE_STATES:
                return idx
        return len(_STEPS) - 1

    def _refresh_tracker(self) -> None:
        tracker = self.query_one("#wizard-progress", ProgressTracker)
        tracker.current_step = self._current_step
        tracker.completed_steps = frozenset(
            idx for idx, status in self._step_states.items() if status == "success"
        )
        tracker.failed_steps = frozenset(
            idx for idx, status in self._step_states.items() if status == "failed"
        )
        tracker.skipped_steps = frozenset(
            idx for idx, status in self._step_states.items() if status == "skipped"
        )

    def _append_step_note(self, step: int, note: str) -> None:
        if not note:
            return
        notes = self._step_notes.setdefault(step, [])
        if not notes or notes[-1] != note:
            notes.append(note)
        if len(notes) > 6:
            del notes[:-6]

    def _set_step_status(self, step: int, status: str, note: str | None = None) -> None:
        self._step_states[step] = status
        if note:
            self._append_step_note(step, note)
        self._persist_state()
        self._refresh_tracker()

    def _state_color(self, status: str) -> str:
        if status == "success":
            return "#39ff14"
        if status == "failed":
            return "#ff3366"
        if status == "running":
            return "#00ffcc"
        if status == "skipped":
            return "#ffaa00"
        return "#8892a4"

    def _workflow_label(self) -> str:
        if self._workflow_mode == "train_then_deploy":
            return "Train then Deploy"
        return "Deploy Existing Weights"

    def _template_name(self) -> str:
        if self._project and self._project.template:
            return str(self._project.template)
        return "unknown"

    def _template_capability_lines(self) -> list[str]:
        template = self._template_name().lower()
        capability = _TEMPLATE_CAPABILITIES.get(template)
        if capability is None:
            return [
                f"[#8892a4]Template:[/] {self._template_name()}",
                "[#8892a4]Capability:[/] Unknown template capability",
            ]
        return [
            f"[#8892a4]Template:[/] {template}",
            f"[#8892a4]Capability:[/] {capability}",
        ]

    def _set_workflow_mode(self, mode: str) -> None:
        if mode not in _WORKFLOW_MODES or mode == self._workflow_mode or self._busy:
            return
        self._workflow_mode = mode
        # Step 2 semantics differ by workflow; clear previous result.
        self._step_states[2] = "pending"
        self._step_notes.pop(2, None)
        self._persist_state()
        self._render_step()
        self._log("info", f"Workflow set: {self._workflow_label()}")
        self.notify(f"Workflow: {self._workflow_label()}", severity="information")

    def action_cycle_workflow(self) -> None:
        if self._workflow_mode == "deploy_existing":
            self._set_workflow_mode("train_then_deploy")
        else:
            self._set_workflow_mode("deploy_existing")

    def action_select_workflow_deploy_existing(self) -> None:
        self._set_workflow_mode("deploy_existing")

    def action_select_workflow_train_then_deploy(self) -> None:
        self._set_workflow_mode("train_then_deploy")

    def _find_training_data_path(self) -> Path | None:
        project = self._project
        if project is None:
            return None
        candidates = [
            "train.csv",
            "data.csv",
            "dataset.csv",
            "train.npz",
            "data.npz",
            "dataset.npz",
            "data/train.csv",
            "data/train.npz",
            "datasets/train.csv",
            "datasets/train.npz",
        ]
        for rel in candidates:
            path = project.path / rel
            if path.exists() and path.is_file():
                return path
        return None

    def _default_training_task(self) -> str:
        template = self._template_name().lower()
        if template in {"softmax", "naive_bayes"}:
            return "classification"
        return "regression"

    def _step_guidance(self, step: int) -> list[str]:
        if step == 0:
            lines = [
                "[#8892a4]Confirm project paths and template before running deployment.[/]",
                f"[#8892a4]Workflow:[/] {self._workflow_label()}",
                "[#8892a4]Press [#00ffcc]1[/] deploy-existing or [#00ffcc]2[/] train-then-deploy (or [#00ffcc]W[/] to toggle).[/]",
            ]
            lines.extend(self._template_capability_lines())
            if self._template_name().lower() == "custom":
                lines.append(
                    "[#ffaa00]Custom guest is a scaffold example. Replace guest logic for real custom architectures.[/]"
                )
            return lines
        if step == 1:
            return [
                "[#8892a4]Validate manifest schema + required sections.[/]",
            ]
        if step == 2:
            if self._workflow_mode == "train_then_deploy":
                return [
                    "[#8892a4]Train from project dataset and auto-generate weights artifacts.[/]",
                    "[#8892a4]Auto-detects: train/data/dataset (*.csv or *.npz) under project paths.[/]",
                    "[#8892a4]If not found, use Power Mode Train panel and retry this step.[/]",
                ]
            return [
                "[#8892a4]Training skipped for deploy-existing workflow.[/]",
                "[#8892a4]Switch workflow with 1/2/W if you want in-TUI training.[/]",
            ]
        if step == 3:
            return [
                "[#8892a4]Pack weights metadata/hashes into the manifest.[/]",
            ]
        if step == 4:
            return [
                "[#8892a4]Build the RISC-V guest binary used for execution.[/]",
            ]
        if step == 5:
            return [
                "[#8892a4]Create accounts config, then allocate PDA accounts on-chain.[/]",
            ]
        if step == 6:
            return [
                "[#8892a4]Chunk weights (if needed) and upload all chunks on-chain.[/]",
            ]
        if step == 7:
            return [
                "[#8892a4]Write input payload to VM scratch memory.[/]",
                "[#8892a4]Wizard will scaffold an input file automatically if missing.[/]",
            ]
        if step == 8:
            return [
                "[#8892a4]Load compiled guest ELF into the VM.[/]",
            ]
        if step == 9:
            return [
                "[#8892a4]Invoke inference execution transaction(s).[/]",
            ]
        if step == 10:
            return [
                "[#8892a4]Read output bytes and decode according to manifest schema.[/]",
            ]
        return []

    def _render_step_status_overview(self) -> list[str]:
        lines: list[str] = ["[#8892a4]Pipeline Status[/]"]
        for idx, step_name in enumerate(_STEPS):
            status = self._step_states.get(idx, "pending")
            color = self._state_color(status)
            marker = ">"
            if idx != self._current_step:
                marker = " "
            lines.append(
                f"[#555e6e]{marker}[/] [#8892a4]{idx:02d}[/] "
                f"[#e0e6f0]{step_name:<11}[/] [{color}]{status.upper()}[/]"
            )
        return lines

    def _render_completion_summary(self) -> list[str]:
        if not self._is_complete():
            return []
        lines = ["[#39ff14 bold]Wizard complete. End-to-end flow finished in Wizard mode.[/]"]
        lines.append(f"[#8892a4]Workflow:[/] {self._workflow_label()}")
        if self._project and self._project.accounts_path:
            lines.append(f"[#8892a4]Accounts:[/] {self._project.accounts_path}")
        if self._generated_input_path:
            lines.append(f"[#8892a4]Input payload:[/] {self._generated_input_path}")
        if self._guest_elf_path:
            lines.append(f"[#8892a4]Guest ELF:[/] {self._guest_elf_path}")
        if self._invoke_signature:
            lines.append(f"[#8892a4]Invoke signature:[/] {self._invoke_signature}")
        if self._generated_context_path:
            lines.append(f"[#8892a4]Latest agent context:[/] {self._generated_context_path}")
        if self._output_data is not None:
            output = self._output_data.get("output")
            if isinstance(output, (list, dict)):
                output_text = json.dumps(output)
            else:
                output_text = str(output)
            if len(output_text) > 120:
                output_text = output_text[:117] + "..."
            lines.append(f"[#8892a4]Output preview:[/] {output_text}")
        lines.append("[#8892a4]Press Next to return Home, or C to copy a context bundle for an agent.[/]")
        return lines

    def _render_step(self) -> None:
        self._refresh_tracker()
        content = self.query_one("#wizard-step-content", Static)
        step_name = _STEPS[self._current_step]
        step_state = self._step_states.get(self._current_step, "pending")
        step_color = self._state_color(step_state)

        lines = [
            f"[#00ffcc bold]Step {self._current_step}: {step_name}[/]",
            f"[#8892a4]Status:[/] [{step_color}]{step_state.upper()}[/]",
            "",
        ]
        lines.extend(self._step_guidance(self._current_step))
        notes = self._step_notes.get(self._current_step) or []
        if notes:
            lines.append("")
            lines.append("[#8892a4]Recent step notes:[/]")
            for note in notes[-4:]:
                lines.append(f"[#555e6e]-[/] {note}")

        if self._last_error and step_state == "failed":
            lines.append("")
            lines.append(f"[#ff3366]Last error:[/] {self._last_error}")
            lines.append("[#8892a4]Retry with Enter, go back with Left, or press P for Power Mode.[/]")

        lines.append("")
        lines.extend(self._render_step_status_overview())
        if self._is_complete():
            lines.append("")
            lines.extend(self._render_completion_summary())

        content.update("\n".join(lines))
        self._update_nav_buttons()

    def _is_complete(self) -> bool:
        return all(self._step_states.get(idx) in _COMPLETE_STATES for idx in range(len(_STEPS)))

    def _update_nav_buttons(self) -> None:
        try:
            back = self.query_one("#btn-wiz-back", Button)
            skip = self.query_one("#btn-wiz-skip", Button)
            nxt = self.query_one("#btn-wiz-next", Button)
            context = self.query_one("#btn-wiz-context", Button)
        except Exception:
            return

        back.disabled = self._busy or self._current_step <= 0
        context.disabled = self._busy or self._project is None

        if self._is_complete():
            skip.disabled = True
            nxt.label = "Done"
            nxt.disabled = self._busy
            return

        skip.disabled = self._busy
        current_state = self._step_states.get(self._current_step, "pending")
        if self._busy:
            nxt.label = "Running..."
            nxt.disabled = True
        elif current_state == "failed":
            nxt.label = "Retry"
            nxt.disabled = False
        elif current_state in _COMPLETE_STATES and self._current_step < len(_STEPS) - 1:
            nxt.label = "Next"
            nxt.disabled = False
        elif self._current_step == 2:
            nxt.label = "Skip Train"
            nxt.disabled = False
        else:
            nxt.label = "Run Step"
            nxt.disabled = False

    def _log(self, level: str, message: str) -> None:
        log = self.query_one("#wizard-log", LogPanel)
        if level == "success":
            log.log_success(message)
        elif level == "error":
            log.log_error(message)
        elif level == "warning":
            log.log_warning(message)
        else:
            log.log_info(message)
        self._log_history.append(f"[{level.upper()}] {message}")
        if len(self._log_history) > 250:
            del self._log_history[:-250]

    def _record_result(self, step: int, result: Any) -> bool:
        if bool(getattr(result, "success", False)):
            message = str(getattr(result, "message", "Step complete"))
            self._set_step_status(step, "success", message)
            self._log("success", message)
            for line in list(getattr(result, "logs", []))[:30]:
                self._log("info", f"  {line}")
            return True

        message = str(getattr(result, "message", "Step failed"))
        self._last_error = message
        self._set_step_status(step, "failed", message)
        self._log("error", message)
        for err in list(getattr(result, "errors", []))[:20]:
            self._log("error", f"  {err}")
        for line in list(getattr(result, "logs", []))[:30]:
            self._log("error", f"  {line}")
        self._log("warning", "Retry with Enter, go back with Left, or press P for Power Mode.")
        return False

    def _fail_step(self, step: int, message: str) -> bool:
        self._last_error = message
        self._set_step_status(step, "failed", message)
        self._log("error", message)
        self._log("warning", "Retry with Enter, go back with Left, or press P for Power Mode.")
        return False

    def _require_project(self, step: int) -> ProjectInfo | None:
        if self._project is None:
            self._fail_step(step, "No active project loaded.")
            return None
        return self._project

    def _require_accounts_path(self, step: int) -> Path | None:
        project = self._require_project(step)
        if project is None:
            return None
        if project.accounts_path is None:
            self._fail_step(step, "No accounts file registered. Run the Accounts step first.")
            return None
        if not project.accounts_path.exists():
            self._fail_step(step, f"Accounts file missing on disk: {project.accounts_path}")
            return None
        return project.accounts_path

    def _invoke_budget_defaults(self) -> tuple[int, int]:
        template = (self._project.template if self._project else "") or ""
        if template.lower() in _HEAVY_TEMPLATES:
            return 30_000, 20
        return 50_000, 10

    def _guess_guest_binary_path(self) -> Path | None:
        project = self._project
        if project is None:
            return None
        if self._guest_elf_path and self._guest_elf_path.exists():
            return self._guest_elf_path

        base = project.manifest_path.parent / "guest" / "target" / "riscv64imac-unknown-none-elf"
        candidates = [
            base / "release" / "frostbite-guest",
            base / "release" / "guest",
            base / "debug" / "frostbite-guest",
            base / "debug" / "guest",
        ]
        if sys.platform.startswith("win"):
            candidates.extend(
                [
                    base / "release" / "frostbite-guest.exe",
                    base / "release" / "guest.exe",
                    base / "debug" / "frostbite-guest.exe",
                    base / "debug" / "guest.exe",
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _nested_zero_payload(self, shape: list[int], value: int | float) -> Any:
        if not shape:
            return value
        if len(shape) == 1:
            return [value for _ in range(max(1, shape[0]))]
        return [self._nested_zero_payload(shape[1:], value) for _ in range(max(1, shape[0]))]

    def _build_payload_template(self, manifest: dict[str, Any]) -> Any:
        schema = manifest.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("Manifest missing schema table")
        schema_type = schema.get("type")
        if schema_type == "vector":
            vector = schema.get("vector") if isinstance(schema.get("vector"), dict) else {}
            shape = vector.get("input_shape")
            if not isinstance(shape, list) or not shape:
                shape = [1]
            safe_shape = [int(max(1, int(dim))) for dim in shape]
            dtype = str(vector.get("input_dtype", "f32")).lower()
            zero: int | float = 0 if dtype.startswith(("i", "u")) else 0.0
            return self._nested_zero_payload(safe_shape, zero)

        if schema_type == "time_series":
            ts = schema.get("time_series") if isinstance(schema.get("time_series"), dict) else {}
            window = int(max(1, int(ts.get("window", 1))))
            features = int(max(1, int(ts.get("features", 1))))
            dtype = str(ts.get("input_dtype", "f32")).lower()
            zero = 0 if dtype.startswith(("i", "u")) else 0.0
            return [[zero for _ in range(features)] for _ in range(window)]

        if schema_type == "graph":
            graph = schema.get("graph") if isinstance(schema.get("graph"), dict) else {}
            node_dim = int(max(1, int(graph.get("node_feature_dim", 1))))
            edge_dim = int(max(0, int(graph.get("edge_feature_dim", 0))))
            dtype = str(graph.get("input_dtype", "f32")).lower()
            zero = 0 if dtype.startswith(("i", "u")) else 0.0
            payload: dict[str, Any] = {
                "node_count": 1,
                "edge_count": 0,
                "nodes": [[zero for _ in range(node_dim)]],
                "edges": [],
            }
            if edge_dim > 0:
                payload["edge_features"] = []
            return payload

        raise ValueError(f"Unsupported schema type for JSON scaffold: {schema_type}")

    def _prepare_input_payload(self) -> tuple[Path | None, Path | None, str]:
        project = self._project
        if project is None:
            raise ValueError("No active project loaded")
        manifest = load_manifest(project.manifest_path)
        schema = manifest.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("Manifest missing schema table")
        schema_type = schema.get("type")

        existing_candidates = [
            project.path / "input.json",
            project.path / "input.wizard.json",
            project.path / ".cauldron" / "wizard" / "input.json",
        ]
        for candidate in existing_candidates:
            if candidate.exists():
                self._generated_input_path = candidate
                return candidate, None, f"Using existing input JSON: {candidate}"

        wizard_dir = project.path / ".cauldron" / "wizard"
        wizard_dir.mkdir(parents=True, exist_ok=True)

        if schema_type == "custom":
            custom = schema.get("custom") if isinstance(schema.get("custom"), dict) else {}
            size = int(custom.get("input_blob_size", 0))
            if size <= 0:
                raise ValueError("schema.custom.input_blob_size must be a positive integer")
            input_bin = wizard_dir / "input.wizard.bin"
            if not input_bin.exists() or input_bin.stat().st_size < size:
                with input_bin.open("wb") as handle:
                    chunk = b"\x00" * min(size, 8192)
                    remaining = size
                    while remaining > 0:
                        write_now = min(len(chunk), remaining)
                        handle.write(chunk[:write_now])
                        remaining -= write_now
            self._generated_input_path = input_bin
            return None, input_bin, f"Generated custom input scaffold: {input_bin} ({size} bytes)"

        payload = self._build_payload_template(manifest)
        input_json = wizard_dir / "input.wizard.json"
        input_json.write_text(json.dumps({"input": payload}, indent=2) + "\n")
        self._generated_input_path = input_json
        return input_json, None, f"Generated input scaffold: {input_json}"

    async def _execute_step(self, step: int) -> bool:
        project = self._require_project(step)
        if project is None:
            return False

        if step == 0:
            self._set_step_status(step, "success", f"Project ready: {project.name}")
            self._log("success", f"Project ready: {project.name}")
            return True

        if step == 1:
            result = await asyncio.to_thread(cmd_validate, project.manifest_path)
            return self._record_result(step, result)

        if step == 2:
            if self._workflow_mode != "train_then_deploy":
                msg = "Training skipped for deploy-existing workflow."
                self._set_step_status(step, "skipped", msg)
                self._log("warning", msg)
                return True

            data_path = self._find_training_data_path()
            if data_path is None:
                return self._fail_step(
                    step,
                    "No training data found. Add train/data/dataset (.csv or .npz) under project path, "
                    "or use Power Mode Train panel, then retry.",
                )

            task = self._default_training_task()
            self._log("info", f"Training from dataset: {data_path.name} ({task})")
            train_result = await asyncio.to_thread(
                cmd_train,
                manifest_path=project.manifest_path,
                data_path=data_path,
                template=project.template,
                task=task,
            )
            if not self._record_result(step, train_result):
                return False
            self._append_step_note(step, f"Dataset: {data_path}")
            return True

        if step == 3:
            self._log("info", "Packing manifest...")
            result = await asyncio.to_thread(cmd_pack, project.manifest_path, True)
            return self._record_result(step, result)

        if step == 4:
            self._log("info", "Building guest...")
            result = await asyncio.to_thread(cmd_build_guest, project.manifest_path)
            if not self._record_result(step, result):
                return False
            self._guest_elf_path = self._guess_guest_binary_path()
            if self._guest_elf_path:
                self._append_step_note(step, f"Guest ELF: {self._guest_elf_path}")
            return True

        if step == 5:
            self._log("info", "Generating accounts config...")
            init_result = await asyncio.to_thread(cmd_accounts_init, project.manifest_path)
            if not self._record_result(step, init_result):
                return False
            accounts_path = init_result.data.get("path")
            if not isinstance(accounts_path, str):
                return self._fail_step(step, "Accounts init did not return an accounts file path")
            project.accounts_path = Path(accounts_path)
            self._append_step_note(step, f"Accounts file: {project.accounts_path}")

            self._log("info", "Creating PDA accounts on-chain...")
            create_result = await asyncio.to_thread(cmd_accounts_create, project.accounts_path)
            if not self._record_result(step, create_result):
                return False
            return True

        if step == 6:
            accounts_path = self._require_accounts_path(step)
            if accounts_path is None:
                return False
            self._log("info", "Ensuring chunk files exist...")
            chunk_result = await asyncio.to_thread(cmd_chunk, project.manifest_path)
            if not self._record_result(step, chunk_result):
                return False
            chunk_paths = [Path(p) for p in chunk_result.data.get("chunks", []) if isinstance(p, str)]
            if not chunk_paths:
                return self._fail_step(step, "No chunks produced for upload")

            for idx, chunk_path in enumerate(chunk_paths, start=1):
                self._log("info", f"Uploading chunk {idx}/{len(chunk_paths)}: {chunk_path.name}")
                upload_result = await asyncio.to_thread(
                    cmd_upload,
                    file_path=chunk_path,
                    accounts_path=accounts_path,
                )
                if not bool(getattr(upload_result, "success", False)):
                    return self._record_result(step, upload_result)
            self._set_step_status(step, "success", f"Uploaded {len(chunk_paths)} chunk(s)")
            self._log("success", f"Uploaded {len(chunk_paths)} chunk(s)")
            return True

        if step == 7:
            accounts_path = self._require_accounts_path(step)
            if accounts_path is None:
                return False
            try:
                data_path, input_bin, note = self._prepare_input_payload()
            except Exception as exc:
                return self._fail_step(step, str(exc))
            self._log("info", note)
            write_result = await asyncio.to_thread(
                cmd_input_write,
                project.manifest_path,
                accounts_path,
                data_path=data_path,
                input_bin=input_bin,
            )
            return self._record_result(step, write_result)

        if step == 8:
            accounts_path = self._require_accounts_path(step)
            if accounts_path is None:
                return False
            guest_elf = self._guess_guest_binary_path()
            if guest_elf is None:
                return self._fail_step(step, "Guest ELF not found. Build guest first.")
            self._guest_elf_path = guest_elf
            self._log("info", f"Loading guest program: {guest_elf.name}")
            load_result = await asyncio.to_thread(
                cmd_program_load,
                program_path=guest_elf,
                accounts_path=accounts_path,
            )
            return self._record_result(step, load_result)

        if step == 9:
            accounts_path = self._require_accounts_path(step)
            if accounts_path is None:
                return False
            instructions, max_tx = self._invoke_budget_defaults()
            self._log("info", f"Invoking (resume mode, instructions={instructions}, max_tx={max_tx})...")
            invoke_result = await asyncio.to_thread(
                cmd_invoke,
                accounts_path=accounts_path,
                mode="resume",
                instructions=instructions,
                max_tx=max_tx,
            )
            if not bool(getattr(invoke_result, "success", False)):
                self._log("warning", "Resume invoke failed; retrying in fresh mode.")
                invoke_result = await asyncio.to_thread(
                    cmd_invoke,
                    accounts_path=accounts_path,
                    mode="fresh",
                    instructions=instructions,
                    max_tx=max_tx,
                )
            if not self._record_result(step, invoke_result):
                return False
            signature = invoke_result.data.get("signature")
            if isinstance(signature, str) and signature:
                self._invoke_signature = signature
                self._append_step_note(step, f"Signature: {signature}")
            return True

        if step == 10:
            accounts_path = self._require_accounts_path(step)
            if accounts_path is None:
                return False
            self._log("info", "Reading output from chain...")
            output_result = await asyncio.to_thread(
                cmd_output,
                manifest_path=project.manifest_path,
                accounts_path=accounts_path,
                after_signature=self._invoke_signature,
            )
            if not self._record_result(step, output_result):
                return False
            if isinstance(output_result.data, dict):
                self._output_data = dict(output_result.data)
            return True

        return self._fail_step(step, f"Unhandled step index: {step}")

    async def _run_current_step(self) -> None:
        if self._busy:
            return
        if self._is_complete() and self._current_step == len(_STEPS) - 1:
            self.action_go_home()
            return

        current_state = self._step_states.get(self._current_step, "pending")
        if current_state in _COMPLETE_STATES and self._current_step < len(_STEPS) - 1:
            self._current_step += 1
            self._persist_state()
            self._render_step()
            return

        step = self._current_step
        self._busy = True
        self._set_step_status(step, "running", f"Running step {step}: {_STEPS[step]}")
        self._render_step()
        succeeded = False
        try:
            succeeded = await self._execute_step(step)
        except Exception as exc:
            self._fail_step(step, str(exc))
        finally:
            self._busy = False

        if succeeded:
            if step < len(_STEPS) - 1:
                self._current_step += 1
            elif self._is_complete():
                self._append_step_note(step, "Wizard complete")

        self._persist_state()
        self._render_step()

    async def action_next_step(self) -> None:
        await self._run_current_step()

    def action_back_step(self) -> None:
        if self._busy:
            return
        if self._current_step > 0:
            self._current_step -= 1
            self._persist_state()
            self._render_step()

    def action_skip_step(self) -> None:
        if self._busy or self._is_complete():
            return
        step = self._current_step
        self._set_step_status(step, "skipped", "Step skipped by user")
        self._log("warning", f"Skipped step {step}: {_STEPS[step]}")
        if step < len(_STEPS) - 1:
            self._current_step += 1
        self._persist_state()
        self._render_step()

    def export_agent_context_payload(self) -> dict[str, Any]:
        return {
            "source": "wizard",
            "workflow_mode": self._workflow_mode,
            "step_index": self._current_step,
            "step_name": _STEPS[self._current_step],
            "step_states": dict(self._step_states),
            "logs": list(self._log_history),
            "last_error": self._last_error,
            "invoke_signature": self._invoke_signature,
            "output_data": self._output_data,
        }

    def action_copy_context(self) -> None:
        project = self._project
        if project is None:
            self.notify("No active project", severity="warning")
            return
        payload = self.export_agent_context_payload()
        context_text = render_agent_context(project=project, **payload)
        out_path = write_agent_context(project.path, context_text)
        self._generated_context_path = out_path
        copied, tool_msg = copy_text_to_clipboard(context_text)
        if copied:
            self.notify(f"Agent context saved and copied ({tool_msg})", severity="information")
            self._log("success", f"Agent context copied ({tool_msg}) and saved: {out_path}")
        else:
            self.notify(f"Agent context saved ({tool_msg})", severity="warning")
            self._log("warning", f"Agent context saved (clipboard unavailable): {out_path}")
        self._render_step()

    def action_open_power(self) -> None:
        from .power import PowerScreen

        self.app.pop_screen()
        self.app.push_screen(PowerScreen())

    def action_go_home(self) -> None:
        if hasattr(self.app, "action_home"):
            self.app.action_home()
        else:
            self.app.pop_screen()
