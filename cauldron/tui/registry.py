"""Project registry — persists known projects at ~/.cauldron/projects.toml."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import ProjectInfo

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

REGISTRY_DIR = Path.home() / ".cauldron"
REGISTRY_PATH = REGISTRY_DIR / "projects.toml"

_DEFAULT_REGISTRY: dict[str, Any] = {
    "registry": {
        "version": 1,
        "default_cluster": "devnet",
        "default_rpc_url": "https://api.devnet.solana.com",
        "default_payer": str(Path.home() / ".config" / "solana" / "id.json"),
    },
    "projects": [],
}


def _fresh_default_registry() -> dict[str, Any]:
    return {
        "registry": dict(_DEFAULT_REGISTRY["registry"]),
        "projects": [],
    }


def _ensure_dir() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)


def load_registry() -> dict[str, Any]:
    """Load or create the registry."""
    if not REGISTRY_PATH.exists():
        _ensure_dir()
        defaults = _fresh_default_registry()
        save_registry(defaults)
        return defaults
    return tomllib.loads(REGISTRY_PATH.read_text())


def save_registry(data: dict[str, Any]) -> None:
    """Write registry to disk."""
    _ensure_dir()
    REGISTRY_PATH.write_bytes(tomli_w.dumps(data).encode())


def _project_to_dict(p: ProjectInfo) -> dict[str, Any]:
    project_name = (p.name or p.path.name or str(p.path)).strip()
    d: dict[str, Any] = {
        "name": project_name,
        "path": str(p.path),
        "manifest": str(p.manifest_path),
    }
    if p.accounts_path:
        d["accounts"] = str(p.accounts_path)
    if p.template:
        d["template"] = p.template
    if p.cluster:
        d["cluster"] = p.cluster
    if p.rpc_url:
        d["rpc_url"] = p.rpc_url
    if p.program_id:
        d["program_id"] = p.program_id
    if p.payer:
        d["payer"] = p.payer
    if p.last_activity:
        d["last_activity"] = p.last_activity
    d["deployment_state"] = p.deployment_state
    return d


def _dict_to_project(d: dict[str, Any]) -> ProjectInfo:
    path = Path(d["path"])
    raw_name = d.get("name")
    project_name = str(raw_name).strip() if raw_name is not None else ""
    if not project_name:
        project_name = path.name or str(path)
    return ProjectInfo(
        name=project_name,
        path=path,
        manifest_path=Path(d["manifest"]),
        accounts_path=Path(d["accounts"]) if d.get("accounts") else None,
        template=d.get("template"),
        cluster=d.get("cluster"),
        rpc_url=d.get("rpc_url"),
        program_id=d.get("program_id"),
        payer=d.get("payer"),
        last_activity=d.get("last_activity"),
        deployment_state=d.get("deployment_state", "init"),
    )


def list_projects() -> list[ProjectInfo]:
    """Return all registered projects."""
    reg = load_registry()
    return [_dict_to_project(p) for p in reg.get("projects", [])]


def get_project(name: str) -> ProjectInfo | None:
    """Get a project by name."""
    for p in list_projects():
        if p.name == name:
            return p
    return None


def register_project(project: ProjectInfo) -> None:
    """Add or update a project in the registry."""
    reg = load_registry()
    projects = reg.get("projects", [])
    for i, p in enumerate(projects):
        if p.get("name") == project.name or str(p.get("path")) == str(project.path):
            projects[i] = _project_to_dict(project)
            reg["projects"] = projects
            save_registry(reg)
            return
    projects.append(_project_to_dict(project))
    reg["projects"] = projects
    save_registry(reg)


def unregister_project(name: str) -> bool:
    """Remove a project from the registry. Returns True if found."""
    reg = load_registry()
    projects = reg.get("projects", [])
    new = [p for p in projects if p.get("name") != name]
    if len(new) == len(projects):
        return False
    reg["projects"] = new
    save_registry(reg)
    return True


def update_last_activity(name: str) -> None:
    """Touch the last_activity timestamp for a project."""
    reg = load_registry()
    for p in reg.get("projects", []):
        if p.get("name") == name:
            p["last_activity"] = datetime.now(timezone.utc).isoformat()
            break
    save_registry(reg)


def update_deployment_state(name: str, state: str) -> None:
    """Update deployment state for a project."""
    reg = load_registry()
    for p in reg.get("projects", []):
        if p.get("name") == name:
            p["deployment_state"] = state
            p["last_activity"] = datetime.now(timezone.utc).isoformat()
            break
    save_registry(reg)


def discover_project(path: Path) -> ProjectInfo | None:
    """Auto-discover a project by looking for frostbite-model.toml."""
    manifest = path / "frostbite-model.toml"
    if not manifest.exists():
        return None
    try:
        from ..manifest import load_manifest

        m = load_manifest(manifest)
    except Exception:
        return None
    model = m.get("model", {}) if isinstance(m, dict) else {}
    accounts_path = path / "frostbite-accounts.toml"
    return ProjectInfo(
        name=model.get("id", path.name),
        path=path,
        manifest_path=manifest,
        accounts_path=accounts_path if accounts_path.exists() else None,
    )


def get_defaults() -> dict[str, str]:
    """Get registry default settings."""
    reg = load_registry()
    return reg.get("registry", {})


def set_defaults(
    cluster: str | None = None,
    rpc_url: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
) -> None:
    """Update registry default settings."""
    reg = load_registry()
    defaults = reg.setdefault("registry", {})
    if cluster is not None:
        defaults["default_cluster"] = cluster
    if rpc_url is not None:
        defaults["default_rpc_url"] = rpc_url
    if payer is not None:
        defaults["default_payer"] = payer
    if program_id is not None:
        defaults["default_program_id"] = program_id
    save_registry(reg)
