"""Account mapping helpers for Frostbite."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

SEED_DOMAIN = "frostbite-v1"
SEED_VM = "vm"
SEED_SEG = "seg"
SEED_MODEL_SEEDED = "seeded"
SEED_MODEL_PDA = "pda"

SEEDED_VM_PREFIX = "fbv1:vm:"
SEEDED_SEG_PREFIX = "fbv1:sg:"

SEGMENT_KIND_WEIGHTS = 1
SEGMENT_KIND_RAM = 2


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
    resolved = str(Path(path).expanduser())
    result = subprocess.run(
        ["solana-keygen", "pubkey", resolved],
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


def parse_vm_seed(vm_entry: Dict[str, Any]) -> Optional[int]:
    raw = vm_entry.get("seed")
    if raw is None:
        return None
    if isinstance(raw, int):
        if raw < 0 or raw > (2**64 - 1):
            raise ValueError("vm.seed must be within u64 range")
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.lower().startswith("0x"):
            value = int(text, 16)
        else:
            value = int(text, 10)
        if value < 0 or value > (2**64 - 1):
            raise ValueError("vm.seed must be within u64 range")
        return value
    raise ValueError("vm.seed must be an integer or string")


def parse_account_model(vm_entry: Dict[str, Any]) -> Optional[str]:
    raw = vm_entry.get("account_model")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("vm.account_model must be a string")
    value = raw.strip().lower()
    if value in {SEED_MODEL_SEEDED, SEED_MODEL_PDA}:
        return value
    raise ValueError("vm.account_model must be 'seeded' or 'pda'")


def resolve_authority_pubkey(
    accounts: Dict[str, Any],
    authority_keypair_override: Optional[str] = None,
) -> Optional[str]:
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    if isinstance(vm.get("authority"), str) and vm.get("authority"):
        return vm["authority"]
    if authority_keypair_override:
        return _resolve_pubkey_from_keypair(authority_keypair_override)
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        return _resolve_pubkey_from_keypair(vm["authority_keypair"])

    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    if isinstance(cluster.get("payer"), str) and cluster.get("payer"):
        return _resolve_pubkey_from_keypair(cluster["payer"])
    return None


def segment_kind_code(kind: str) -> Optional[int]:
    value = kind.strip().lower()
    if value == "weights":
        return SEGMENT_KIND_WEIGHTS
    if value == "ram":
        return SEGMENT_KIND_RAM
    return None


def _find_program_derived_address(program_id: str, seeds: List[str]) -> str:
    cmd = [
        "solana",
        "find-program-derived-address",
        "--output",
        "json-compact",
        "--no-address-labels",
        program_id,
        *seeds,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "solana find-program-derived-address failed"
        raise RuntimeError(msg)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unable to parse PDA output: {result.stdout.strip()}") from exc
    address = parsed.get("address")
    if not isinstance(address, str) or not address:
        raise RuntimeError(f"PDA output missing address: {result.stdout.strip()}")
    return address


def _create_address_with_seed(program_id: str, authority_pubkey: str, seed: str) -> str:
    cmd = [
        "solana",
        "create-address-with-seed",
        "--no-address-labels",
        "--from",
        authority_pubkey,
        seed,
        program_id,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "solana create-address-with-seed failed"
        raise RuntimeError(msg)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("create-address-with-seed output missing address")
    address = lines[-1]
    if " " in address:
        address = address.split()[-1]
    if not address:
        raise RuntimeError("create-address-with-seed output missing address")
    return address


def vm_seed_string(vm_seed: int) -> str:
    if vm_seed < 0 or vm_seed > (2**64 - 1):
        raise ValueError("vm.seed must be within u64 range")
    return f"{SEEDED_VM_PREFIX}{vm_seed:016x}"


def segment_seed_string(vm_seed: int, kind: int, slot: int) -> str:
    if vm_seed < 0 or vm_seed > (2**64 - 1):
        raise ValueError("vm.seed must be within u64 range")
    if kind < 0 or kind > 0xFF:
        raise ValueError("segment kind must fit in u8")
    if slot < 0 or slot > 0xFF:
        raise ValueError("segment slot must fit in u8")
    return f"{SEEDED_SEG_PREFIX}{vm_seed:016x}:{kind:02x}{slot:02x}"


def derive_vm_pda_legacy(program_id: str, authority_pubkey: str, vm_seed: int) -> str:
    return _find_program_derived_address(
        program_id,
        [
            f"string:{SEED_DOMAIN}",
            f"string:{SEED_VM}",
            f"pubkey:{authority_pubkey}",
            f"u64le:{vm_seed}",
        ],
    )


def derive_segment_pda_legacy(
    program_id: str,
    authority_pubkey: str,
    vm_seed: int,
    kind: int,
    slot: int,
) -> str:
    return _find_program_derived_address(
        program_id,
        [
            f"string:{SEED_DOMAIN}",
            f"string:{SEED_SEG}",
            f"pubkey:{authority_pubkey}",
            f"u64le:{vm_seed}",
            f"u8:{kind}",
            f"u8:{slot}",
        ],
    )


def derive_vm_seeded(program_id: str, authority_pubkey: str, vm_seed: int) -> str:
    return _create_address_with_seed(program_id, authority_pubkey, vm_seed_string(vm_seed))


def derive_segment_seeded(
    program_id: str,
    authority_pubkey: str,
    vm_seed: int,
    kind: int,
    slot: int,
) -> str:
    seed = segment_seed_string(vm_seed, kind, slot)
    return _create_address_with_seed(program_id, authority_pubkey, seed)


def derive_vm_pda(program_id: str, authority_pubkey: str, vm_seed: int) -> str:
    return derive_vm_seeded(program_id, authority_pubkey, vm_seed)


def derive_segment_pda(
    program_id: str,
    authority_pubkey: str,
    vm_seed: int,
    kind: int,
    slot: int,
) -> str:
    return derive_segment_seeded(program_id, authority_pubkey, vm_seed, kind, slot)


@dataclass
class Segment:
    index: int
    slot: int
    kind: str
    pubkey: Optional[str]
    keypair: Optional[str]
    writable: bool
    bytes: Optional[int]


def parse_segments(accounts: Dict[str, Any]) -> List[Segment]:
    raw = accounts.get("segments")
    if not isinstance(raw, list):
        return []
    segments: List[Segment] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        seg_index = item.get("index", idx)
        slot = item.get("slot", seg_index)
        kind = item.get("kind", "custom")
        writable = bool(item.get("writable", False))
        pubkey = item.get("pubkey") if isinstance(item.get("pubkey"), str) else None
        keypair = item.get("keypair") if isinstance(item.get("keypair"), str) else None
        bytes_raw = item.get("bytes")
        payload_bytes = int(bytes_raw) if isinstance(bytes_raw, int) else None
        segments.append(
            Segment(
                index=int(seg_index),
                slot=int(slot),
                kind=str(kind),
                pubkey=pubkey,
                keypair=keypair,
                writable=writable,
                bytes=payload_bytes,
            )
        )
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
    if isinstance(vm.get("seed"), int):
        lines.append(f"seed = {vm['seed']}")
    if isinstance(vm.get("account_model"), str) and vm.get("account_model"):
        lines.append(f"account_model = \"{vm['account_model']}\"")
    if isinstance(vm.get("authority"), str) and vm.get("authority"):
        lines.append(f"authority = \"{vm['authority']}\"")
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        lines.append(f"authority_keypair = \"{vm['authority_keypair']}\"")
    lines.append("")

    segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        lines.append("[[segments]]")
        if "index" in segment:
            lines.append(f"index = {segment['index']}")
        if "slot" in segment:
            lines.append(f"slot = {segment['slot']}")
        if "kind" in segment:
            lines.append(f"kind = \"{segment['kind']}\"")
        if "pubkey" in segment and segment["pubkey"]:
            lines.append(f"pubkey = \"{segment['pubkey']}\"")
        if "keypair" in segment and segment["keypair"]:
            lines.append(f"keypair = \"{segment['keypair']}\"")
        if "bytes" in segment and isinstance(segment["bytes"], int):
            lines.append(f"bytes = {segment['bytes']}")
        lines.append(f"writable = {'true' if segment.get('writable') else 'false'}")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n")
