"""Account mapping helpers for Frostbite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # Python 3.11+
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    return tomllib.loads(path.read_text())


def load_accounts(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Accounts file not found: {path}")
    return _load_toml(path)


def _resolve_pubkey_from_keypair(path: str) -> str:
    result = subprocess.run(
        ["solana-keygen", "pubkey", path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "solana-keygen failed"
        raise RuntimeError(msg)
    return result.stdout.strip()


def resolve_pubkey(entry: Dict[str, Any]) -> Optional[str]:
    pubkey = entry.get("pubkey")
    if isinstance(pubkey, str) and pubkey:
        return pubkey
    keypair = entry.get("keypair")
    if isinstance(keypair, str) and keypair:
        return _resolve_pubkey_from_keypair(keypair)
    return None


@dataclass
class Segment:
    index: int
    kind: str
    pubkey: Optional[str]
    keypair: Optional[str]
    writable: bool


def parse_segments(accounts: Dict[str, Any]) -> List[Segment]:
    raw = accounts.get("segments")
    if not isinstance(raw, list):
        return []
    segments: List[Segment] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        seg_index = item.get("index", idx)
        kind = item.get("kind", "custom")
        writable = bool(item.get("writable", False))
        pubkey = item.get("pubkey") if isinstance(item.get("pubkey"), str) else None
        keypair = item.get("keypair") if isinstance(item.get("keypair"), str) else None
        segments.append(Segment(index=int(seg_index), kind=str(kind), pubkey=pubkey, keypair=keypair, writable=writable))
    segments.sort(key=lambda s: s.index)
    return segments


def write_accounts(path: Path, data: Dict[str, Any]) -> None:
    lines: List[str] = []
    cluster = data.get("cluster") if isinstance(data.get("cluster"), dict) else {}
    if cluster:
        lines.append("[cluster]")
        for key in ("rpc_url", "program_id", "payer"):
            val = cluster.get(key)
            if isinstance(val, str) and val:
                lines.append(f"{key} = \"{val}\"")
        lines.append("")

    vm = data.get("vm") if isinstance(data.get("vm"), dict) else {}
    lines.append("[vm]")
    if isinstance(vm.get("pubkey"), str) and vm.get("pubkey"):
        lines.append(f"pubkey = \"{vm['pubkey']}\"")
    if isinstance(vm.get("keypair"), str) and vm.get("keypair"):
        lines.append(f"keypair = \"{vm['keypair']}\"")
    lines.append("")

    segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        lines.append("[[segments]]")
        if "index" in segment:
            lines.append(f"index = {segment['index']}")
        if "kind" in segment:
            lines.append(f"kind = \"{segment['kind']}\"")
        if "pubkey" in segment and segment["pubkey"]:
            lines.append(f"pubkey = \"{segment['pubkey']}\"")
        if "keypair" in segment and segment["keypair"]:
            lines.append(f"keypair = \"{segment['keypair']}\"")
        lines.append(f"writable = {'true' if segment.get('writable') else 'false'}")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n")
