"""Helpers to export a compact project context bundle for coding agents."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import ProjectInfo


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _status_lines(step_states: dict[int, str] | None) -> list[str]:
    if not step_states:
        return []
    lines: list[str] = []
    for step_idx in sorted(step_states):
        lines.append(f"- step_{step_idx}: {step_states[step_idx]}")
    return lines


def render_agent_context(
    *,
    source: str,
    project: ProjectInfo,
    workflow_mode: str | None = None,
    step_index: int | None = None,
    step_name: str | None = None,
    step_states: dict[int, str] | None = None,
    current_panel: str | None = None,
    logs: list[str] | None = None,
    last_error: str | None = None,
    invoke_signature: str | None = None,
    output_data: dict[str, Any] | None = None,
) -> str:
    """Render a markdown context bundle for coding-agent handoff."""
    lines: list[str] = []
    lines.append("# Cauldron TUI Context")
    lines.append("")
    lines.append(f"- generated_utc: {_iso_now()}")
    lines.append(f"- source: {source}")
    lines.append(f"- project_name: {project.name}")
    lines.append(f"- project_path: {project.path}")
    lines.append(f"- manifest_path: {project.manifest_path}")
    lines.append(f"- accounts_path: {project.accounts_path if project.accounts_path else '(none)'}")
    lines.append(f"- cluster: {project.cluster or 'devnet'}")
    lines.append(f"- rpc_url: {project.rpc_url or '(from accounts/solana config)'}")
    lines.append(f"- program_id: {project.program_id or '(from accounts/solana config)'}")
    lines.append(f"- payer: {project.payer or '(from accounts/solana config)'}")
    if current_panel:
        lines.append(f"- current_panel: {current_panel}")
    if workflow_mode:
        lines.append(f"- workflow_mode: {workflow_mode}")
    if step_index is not None:
        lines.append(f"- wizard_step_index: {step_index}")
    if step_name:
        lines.append(f"- wizard_step_name: {step_name}")
    if invoke_signature:
        lines.append(f"- invoke_signature: {invoke_signature}")
    if last_error:
        lines.append(f"- last_error: {last_error}")

    status = _status_lines(step_states)
    if status:
        lines.append("")
        lines.append("## Wizard Step Status")
        lines.extend(status)

    if output_data:
        lines.append("")
        lines.append("## Latest Output")
        lines.append("```json")
        lines.append(json.dumps(output_data, indent=2, sort_keys=True))
        lines.append("```")

    if logs:
        lines.append("")
        lines.append("## Recent Logs")
        lines.append("```text")
        for entry in logs[-80:]:
            lines.append(entry)
        lines.append("```")

    lines.append("")
    lines.append("## Suggested Checks")
    lines.append("- Verify manifest/accounts paths above exist and are current.")
    lines.append("- Re-run the most recent failed wizard step first if `last_error` is present.")
    lines.append("- Use this context as the opening prompt payload for your coding agent.")
    lines.append("")
    return "\n".join(lines)


def write_agent_context(project_path: Path, context_text: str) -> Path:
    """Write context markdown under project-local `.cauldron/context/`."""
    out_dir = project_path / ".cauldron" / "context"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"agent-context-{stamp}.md"
    out_path.write_text(context_text)
    return out_path


def copy_text_to_clipboard(text: str) -> tuple[bool, str]:
    """Best-effort clipboard copy across common platforms."""
    system = platform.system().lower()
    candidates: list[list[str]] = []
    if system == "darwin":
        candidates.append(["pbcopy"])
    elif system == "windows":
        candidates.append(["clip"])
    else:
        candidates.extend(
            [
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]
        )

    for cmd in candidates:
        exe = cmd[0]
        if shutil.which(exe) is None:
            continue
        try:
            subprocess.run(cmd, input=text, text=True, check=True, capture_output=True)
            return True, exe
        except Exception:
            continue
    return False, "no supported clipboard command found"
