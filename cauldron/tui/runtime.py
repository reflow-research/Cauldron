"""Runtime context helpers for consistent cluster/RPC/program/payer resolution."""

from __future__ import annotations

from dataclasses import dataclass

from ..helpers import CLUSTER_URLS
from .registry import get_defaults
from .state import ProjectInfo


@dataclass(frozen=True)
class RuntimeContext:
    """Resolved runtime values used by TUI command wrappers."""

    cluster: str
    rpc_url: str | None
    program_id: str | None
    payer: str | None


def _clean(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def resolve_runtime_context(project: ProjectInfo | None) -> RuntimeContext:
    """Resolve cluster/RPC/program/payer from project fields and registry defaults."""

    defaults = get_defaults()

    project_cluster = _clean(project.cluster) if project else None
    default_cluster = _clean(defaults.get("default_cluster"))
    cluster = project_cluster or default_cluster or "devnet"

    project_rpc = _clean(project.rpc_url) if project else None
    default_rpc = _clean(defaults.get("default_rpc_url"))
    rpc_url = project_rpc or default_rpc or CLUSTER_URLS.get(cluster)

    project_program_id = _clean(project.program_id) if project else None
    default_program_id = _clean(defaults.get("default_program_id"))
    program_id = project_program_id or default_program_id

    project_payer = _clean(project.payer) if project else None
    default_payer = _clean(defaults.get("default_payer"))
    payer = project_payer or default_payer

    return RuntimeContext(
        cluster=cluster,
        rpc_url=rpc_url,
        program_id=program_id,
        payer=payer,
    )

