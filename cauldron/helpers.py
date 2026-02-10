"""Shared helpers extracted from cli.py for reuse by the TUI and commands API.

All functions here were originally private (_-prefixed) in cli.py.  cli.py now
imports them from this module so behaviour is identical.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import re
import struct
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .accounts import (
    derive_segment_pda,
    derive_vm_pda,
    load_accounts,
    parse_segments,
    parse_vm_entry,
    parse_vm_seed,
    resolve_authority_pubkey,
    resolve_pubkey,
    segment_kind_code,
)
from .constants import (
    ABI_VERSION,
    DEFAULT_PROGRAM_ID,
    DTYPE_SIZES,
    FBM1_MAGIC,
    MMU_VM_HEADER_SIZE,
)

# ── Regex ──────────────────────────────────────────────────────────

EXEC_SIG_RE = re.compile(r"TX exec-\d+ sig:\s*([1-9A-HJ-NP-Za-km-z]+)")

# ── Cluster URLs ───────────────────────────────────────────────────

CLUSTER_URLS: dict[str, str] = {
    "localnet": "http://127.0.0.1:8899",
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}

# ── Source-upload guard ────────────────────────────────────────────

SOURCE_UPLOAD_SUFFIXES: set[str] = {
    ".json", ".npz", ".npy", ".pt", ".pth",
    ".safetensors", ".toml", ".yaml", ".yml", ".csv", ".txt",
}

# ── Platform / runner resolution ───────────────────────────────────


def platform_tag() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "darwin-arm64"
        if machine in {"x86_64", "amd64"}:
            return "darwin-x64"
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "linux-x64"
        if machine in {"arm64", "aarch64"}:
            return "linux-arm64"
    if system == "windows":
        if machine in {"x86_64", "amd64"}:
            return "windows-x64"
    return None


def runner_filename() -> str:
    if platform.system().lower() == "windows":
        return "frostbite-run-onchain.exe"
    return "frostbite-run-onchain"


def resolve_run_onchain() -> str:
    env_path = os.environ.get("FROSTBITE_RUN_ONCHAIN")
    if env_path:
        return env_path
    package_dir = Path(__file__).resolve().parent
    runner = runner_filename()
    tag = platform_tag()
    if tag:
        bundled = package_dir / "bin" / tag / runner
        if bundled.exists():
            return str(bundled)
        toolchain_bin = package_dir / "toolchain" / "bin" / tag / runner
        if toolchain_bin.exists():
            return str(toolchain_bin)
    bundled = package_dir / "bin" / runner
    if bundled.exists():
        return str(bundled)
    toolchain_bin = package_dir / "toolchain" / "bin" / runner
    if toolchain_bin.exists():
        return str(toolchain_bin)
    return "frostbite-run-onchain"


# ── Solana CLI config ──────────────────────────────────────────────


def load_solana_cli_config() -> dict[str, str]:
    path = os.environ.get("SOLANA_CONFIG") or os.environ.get("SOLANA_CONFIG_FILE")
    if path:
        cfg_path = Path(path)
    else:
        cfg_path = Path.home() / ".config" / "solana" / "cli" / "config.yml"
    try:
        text = cfg_path.read_text()
    except OSError:
        return {}
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            cfg[key] = value
    return cfg


# ── RPC helpers ────────────────────────────────────────────────────


def rpc_request_raw(url: str, method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    retries = 6
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(0.25 * (2**attempt))
                continue
            raise ValueError(f"RPC HTTP error {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(0.25 * (2**attempt))
                continue
            raise ValueError(f"RPC transport error: {exc}") from exc
    raise ValueError("RPC request failed after retries")


def rpc_request(url: str, method: str, params: list) -> dict:
    data = rpc_request_raw(url, method, params)
    if "error" in data:
        raise ValueError(f"RPC error: {data['error']}")
    return data.get("result", {})


def commitment_satisfied(status: str | None, commitment: str) -> bool:
    if commitment == "processed":
        return status in {"processed", "confirmed", "finalized"}
    if commitment == "confirmed":
        return status in {"confirmed", "finalized"}
    return status == "finalized"


def wait_for_signature_slot(
    rpc_url: str,
    signature: str,
    commitment: str,
    wait_seconds: float,
    poll_interval: float,
) -> int:
    if wait_seconds < 0:
        raise ValueError("--wait-seconds must be >= 0")
    if poll_interval <= 0:
        raise ValueError("--poll-interval must be > 0")
    deadline = time.monotonic() + wait_seconds
    while True:
        result = rpc_request(
            rpc_url,
            "getSignatureStatuses",
            [[signature], {"searchTransactionHistory": True}],
        )
        entries = result.get("value") if isinstance(result, dict) else None
        entry = entries[0] if isinstance(entries, list) and entries else None
        if isinstance(entry, dict):
            err = entry.get("err")
            if err is not None:
                raise ValueError(f"Signature {signature} failed: {err}")
            slot = entry.get("slot")
            status = entry.get("confirmationStatus")
            if isinstance(slot, int):
                if commitment == "processed":
                    return slot
                if commitment_satisfied(status, commitment):
                    return slot
        if time.monotonic() >= deadline:
            raise ValueError(
                f"Timed out waiting for signature {signature} to reach {commitment} commitment"
            )
        time.sleep(poll_interval)


# ── Account data fetching ──────────────────────────────────────────


def fetch_account_data(
    rpc_url: str,
    pubkey: str,
    *,
    commitment: str = "confirmed",
    min_context_slot: int | None = None,
    wait_seconds: float = 30.0,
    poll_interval: float = 0.5,
) -> bytes:
    if wait_seconds < 0:
        raise ValueError("--wait-seconds must be >= 0")
    if poll_interval <= 0:
        raise ValueError("--poll-interval must be > 0")
    opts: dict[str, object] = {"encoding": "base64", "commitment": commitment}
    if min_context_slot is not None:
        if min_context_slot < 0:
            raise ValueError("--min-context-slot must be >= 0")
        opts["minContextSlot"] = min_context_slot

    deadline = time.monotonic() + wait_seconds
    while True:
        payload = rpc_request_raw(rpc_url, "getAccountInfo", [pubkey, opts])
        err = payload.get("error")
        if err is not None:
            code = err.get("code") if isinstance(err, dict) else None
            if min_context_slot is not None and code == -32016 and time.monotonic() < deadline:
                time.sleep(poll_interval)
                continue
            raise ValueError(f"RPC error: {err}")

        result = payload.get("result", {})
        value = result.get("value") if isinstance(result, dict) else None
        if value is None:
            raise ValueError("Account not found")
        data = value.get("data") if isinstance(value, dict) else None
        if not data:
            raise ValueError("Account data missing")
        if isinstance(data, list) and data:
            b64 = data[0]
        elif isinstance(data, str):
            b64 = data
        else:
            raise ValueError("Unexpected account data format")
        return base64.b64decode(b64)


# ── Control block / output decoding ────────────────────────────────


def parse_control_block(scratch: bytes, control_offset: int) -> dict[str, int]:
    if control_offset < 0 or control_offset + 64 > len(scratch):
        raise ValueError("control block out of bounds")
    fields = struct.unpack_from("<IIIIIIIIIIIIQ", scratch, control_offset)
    keys = [
        "magic",
        "abi_version",
        "flags",
        "status",
        "input_ptr",
        "input_len",
        "output_ptr",
        "output_len",
        "scratch_ptr",
        "scratch_len",
        "user_ptr",
        "user_len",
        "reserved0",
    ]
    return dict(zip(keys, fields))


def schema_output_info(manifest: dict) -> tuple[str | None, int | None]:
    schema = manifest.get("schema")
    if not isinstance(schema, dict):
        return None, None
    stype = schema.get("type")
    if stype == "vector" and isinstance(schema.get("vector"), dict):
        out_dtype = schema["vector"].get("output_dtype")
        out_shape = schema["vector"].get("output_shape")
    elif stype == "time_series" and isinstance(schema.get("time_series"), dict):
        out_dtype = schema["time_series"].get("output_dtype")
        out_shape = schema["time_series"].get("output_shape")
    elif stype == "graph" and isinstance(schema.get("graph"), dict):
        out_dtype = schema["graph"].get("output_dtype")
        out_shape = schema["graph"].get("output_shape")
    elif stype == "custom" and isinstance(schema.get("custom"), dict):
        out_dtype = "u8"
        out_shape = [schema["custom"].get("output_blob_size")]
    else:
        return None, None

    if not isinstance(out_dtype, str):
        out_dtype = None
    count = None
    if isinstance(out_shape, list) and out_shape:
        try:
            count = 1
            for dim in out_shape:
                count *= int(dim)
        except (TypeError, ValueError):
            count = None
    return out_dtype, count


def decode_output(data: bytes, fmt: str, count: int | None) -> str:
    if fmt == "hex":
        return data.hex()
    if fmt == "raw":
        return "<raw>"
    if fmt == "u8":
        return json.dumps(list(data))

    struct_map = {"i32": "i", "u32": "I", "f32": "f", "i16": "h", "i8": "b", "u8": "B"}
    fmt_char = struct_map.get(fmt)
    if fmt_char is None:
        return data.hex()
    item_size = DTYPE_SIZES.get(fmt)
    if not item_size:
        return data.hex()

    max_items = len(data) // item_size
    if count is None or count > max_items:
        count = max_items
    if count <= 0:
        return "[]"
    fmt_str = "<" + fmt_char * count
    values = struct.unpack_from(fmt_str, data, 0)
    return json.dumps(list(values))


def build_control_block(
    control_size: int,
    input_ptr: int,
    input_len: int,
    output_ptr: int,
    output_len: int,
) -> bytes:
    if control_size < 64:
        raise ValueError("abi.control_size must be >= 64")
    for name, value in (
        ("input_ptr", input_ptr),
        ("input_len", input_len),
        ("output_ptr", output_ptr),
        ("output_len", output_len),
    ):
        if value < 0 or value > 0xFFFF_FFFF:
            raise ValueError(f"{name} must fit in u32")

    buf = bytearray(control_size)
    struct.pack_into(
        "<IIIIIIIIIIIIQ",
        buf,
        0,
        FBM1_MAGIC,
        ABI_VERSION,
        0,
        0,
        input_ptr,
        input_len,
        output_ptr,
        output_len,
        0,
        0,
        0,
        0,
        0,
    )
    return bytes(buf)


# ── Account path resolution ────────────────────────────────────────


def resolve_accounts_path(accounts_path: str, raw_path: str) -> str:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((Path(accounts_path).resolve().parent / candidate).resolve())


def validate_vm_authority_binding(
    accounts_path: str,
    vm: dict[str, object],
    *,
    resolve_pubkey_fn: Any | None = None,
    resolve_accounts_path_fn: Any | None = None,
) -> None:
    if resolve_pubkey_fn is None:
        resolve_pubkey_fn = resolve_pubkey
    if resolve_accounts_path_fn is None:
        resolve_accounts_path_fn = resolve_accounts_path

    authority_raw = vm.get("authority")
    authority_keypair_raw = vm.get("authority_keypair")
    if not isinstance(authority_raw, str) or not authority_raw:
        return
    if not isinstance(authority_keypair_raw, str) or not authority_keypair_raw:
        return

    authority_keypair_pubkey = resolve_pubkey_fn(
        {"keypair": resolve_accounts_path_fn(accounts_path, authority_keypair_raw)}
    )
    if authority_keypair_pubkey and authority_keypair_pubkey != authority_raw:
        raise ValueError(
            "vm.authority does not match vm.authority_keypair pubkey; "
            "update accounts file or signer path"
        )


# ── Account write helper ──────────────────────────────────────────


def write_account(
    env: dict[str, str],
    account_pubkey: str,
    offset: int,
    payload_path: Path,
    chunk_size: int | None,
) -> int:
    if offset < 0 or offset > 0xFFFF_FFFF:
        raise ValueError("offset must fit in u32")
    rust_tools = Path(__file__).resolve().parent / "rust_tools"
    payload_path = payload_path.resolve()
    cmd = [
        "cargo",
        "run",
        "--bin",
        "write_account",
        "--",
        account_pubkey,
        str(offset),
        str(payload_path),
    ]
    if chunk_size:
        cmd.extend(["--chunk-size", str(chunk_size)])
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env, cwd=str(rust_tools))
    return proc.returncode


# ── Environment builders ───────────────────────────────────────────


def build_upload_env(
    *,
    rpc_url: str | None = None,
    cluster: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    solana_cfg = load_solana_cli_config()

    effective_rpc = rpc_url
    if not effective_rpc and cluster:
        if cluster == "surfpool":
            effective_rpc = env.get("SURFPOOL_RPC_URL") or env.get("FROSTBITE_SURFPOOL_RPC_URL")
            if not effective_rpc:
                raise ValueError("surfpool requires --rpc-url or SURFPOOL_RPC_URL")
        else:
            effective_rpc = CLUSTER_URLS.get(cluster)
    if not effective_rpc:
        effective_rpc = env.get("FROSTBITE_RPC_URL") or solana_cfg.get("json_rpc_url")
    if effective_rpc:
        env["FROSTBITE_RPC_URL"] = effective_rpc

    if payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = payer
    elif solana_cfg.get("keypair_path"):
        env.setdefault("FROSTBITE_PAYER_KEYPAIR", solana_cfg["keypair_path"])
    if program_id:
        env["FROSTBITE_PROGRAM_ID"] = program_id
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID
    return env


def apply_accounts_env(
    env: dict[str, str],
    accounts_path: str,
    require_weights_keypair: bool,
    *,
    load_accounts_fn: Any | None = None,
    parse_segments_fn: Any | None = None,
    resolve_accounts_path_fn: Any | None = None,
    validate_vm_authority_binding_fn: Any | None = None,
    resolve_authority_pubkey_fn: Any | None = None,
    resolve_pubkey_fn: Any | None = None,
    parse_vm_seed_fn: Any | None = None,
    segment_kind_code_fn: Any | None = None,
    derive_vm_pda_fn: Any | None = None,
    derive_segment_pda_fn: Any | None = None,
) -> dict[str, str]:
    if load_accounts_fn is None:
        load_accounts_fn = load_accounts
    if parse_segments_fn is None:
        parse_segments_fn = parse_segments
    if resolve_accounts_path_fn is None:
        resolve_accounts_path_fn = resolve_accounts_path
    if validate_vm_authority_binding_fn is None:
        validate_vm_authority_binding_fn = validate_vm_authority_binding
    if resolve_authority_pubkey_fn is None:
        resolve_authority_pubkey_fn = resolve_authority_pubkey
    if resolve_pubkey_fn is None:
        resolve_pubkey_fn = resolve_pubkey
    if parse_vm_seed_fn is None:
        parse_vm_seed_fn = parse_vm_seed
    if segment_kind_code_fn is None:
        segment_kind_code_fn = segment_kind_code
    if derive_vm_pda_fn is None:
        derive_vm_pda_fn = derive_vm_pda
    if derive_segment_pda_fn is None:
        derive_segment_pda_fn = derive_segment_pda

    accounts = load_accounts_fn(accounts_path)
    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    if isinstance(cluster.get("rpc_url"), str) and "FROSTBITE_RPC_URL" not in env:
        env["FROSTBITE_RPC_URL"] = cluster["rpc_url"]
    if isinstance(cluster.get("payer"), str) and "FROSTBITE_PAYER_KEYPAIR" not in env:
        env["FROSTBITE_PAYER_KEYPAIR"] = resolve_accounts_path_fn(accounts_path, cluster["payer"])
    if "FROSTBITE_PROGRAM_ID" not in env:
        if isinstance(cluster.get("program_id"), str):
            env["FROSTBITE_PROGRAM_ID"] = cluster["program_id"]
        else:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    validate_vm_authority_binding_fn(accounts_path, vm)
    authority_keypair_path: str | None = None
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        authority_keypair_path = resolve_accounts_path_fn(accounts_path, vm["authority_keypair"])
        env["FROSTBITE_AUTHORITY_KEYPAIR"] = authority_keypair_path
    if "FROSTBITE_PAYER_KEYPAIR" not in env:
        if authority_keypair_path:
            env["FROSTBITE_PAYER_KEYPAIR"] = authority_keypair_path

    segments = parse_segments_fn(accounts)
    weights = [seg for seg in segments if seg.kind.strip().lower() == "weights"]
    if weights:
        if len(weights) > 1:
            raise ValueError("accounts file has multiple weights segments; single-account mode only")
        seg = weights[0]
        legacy_env_override = env.get("FROSTBITE_CHUNK_KEYPAIR") or env.get("FROSTBITE_WEIGHTS_KEYPAIR")
        vm_seed = parse_vm_seed_fn(vm)
        if vm_seed is not None:
            if legacy_env_override:
                raise ValueError(
                    "vm.seed enables PDA mode; remove FROSTBITE_CHUNK_KEYPAIR/FROSTBITE_WEIGHTS_KEYPAIR override"
                )
            if seg.keypair:
                raise ValueError(
                    "vm.seed enables PDA mode; remove weights segment keypair and use derived PDA metadata"
                )
            _program_id = env.get("FROSTBITE_PROGRAM_ID", DEFAULT_PROGRAM_ID)
            authority_pubkey = resolve_authority_pubkey_fn(
                accounts,
                authority_keypair_override=authority_keypair_path or env.get("FROSTBITE_PAYER_KEYPAIR"),
            )
            if not authority_pubkey:
                raise ValueError(
                    "PDA upload requires authority pubkey; set vm.authority, vm.authority_keypair, "
                    "cluster.payer, or --payer"
                )
            payer_pubkey = None
            if authority_keypair_path is None and "FROSTBITE_PAYER_KEYPAIR" in env:
                payer_pubkey = resolve_pubkey_fn({"keypair": env["FROSTBITE_PAYER_KEYPAIR"]})
            if authority_keypair_path is None and payer_pubkey and authority_pubkey != payer_pubkey:
                raise ValueError(
                    "PDA upload authority differs from payer signer; set vm.authority_keypair "
                    "or use --payer that matches vm.authority"
                )
            env["FROSTBITE_AUTHORITY_PUBKEY"] = authority_pubkey
            env["FROSTBITE_UPLOAD_MODE"] = "pda"
            env["FROSTBITE_VM_SEED"] = str(vm_seed)
            env["FROSTBITE_SEGMENT_KIND"] = "weights"
            if seg.slot != 1:
                raise ValueError("PDA mode requires weights segment at slot 1")
            env["FROSTBITE_SEGMENT_SLOT"] = str(seg.slot)
            derived_vm_pubkey = derive_vm_pda_fn(_program_id, authority_pubkey, vm_seed)
            configured_vm_pubkey = resolve_pubkey_fn(vm)
            if configured_vm_pubkey and configured_vm_pubkey != derived_vm_pubkey:
                raise ValueError(
                    "vm.pubkey does not match derived VM PDA for vm.seed/authority; "
                    "remove vm.pubkey or fix vm.seed/authority"
                )
            env["FROSTBITE_VM_PUBKEY"] = derived_vm_pubkey

            seg_pubkey = seg.pubkey or (
                resolve_pubkey_fn({"keypair": resolve_accounts_path_fn(accounts_path, seg.keypair)})
                if seg.keypair
                else None
            )
            kind_code = segment_kind_code_fn(seg.kind)
            if kind_code is None:
                raise ValueError("weights segment has unsupported kind metadata")
            derived_segment_pubkey = derive_segment_pda_fn(
                _program_id,
                authority_pubkey,
                vm_seed,
                kind_code,
                seg.slot,
            )
            if seg_pubkey and seg_pubkey != derived_segment_pubkey:
                raise ValueError(
                    "weights segment pubkey does not match derived PDA for vm.seed/authority/slot; "
                    "remove segment pubkey/keypair or fix metadata"
                )
            env["FROSTBITE_SEGMENT_PUBKEY"] = derived_segment_pubkey
            return env

        if legacy_env_override:
            return env
        if seg.keypair:
            env["FROSTBITE_CHUNK_KEYPAIR"] = resolve_accounts_path_fn(accounts_path, seg.keypair)
            return env
        if require_weights_keypair:
            raise ValueError("weights segment requires keypair for legacy upload or vm.seed for PDA upload")
    elif require_weights_keypair:
        raise ValueError("accounts file missing weights segment")
    return env


# ── Segment / account metadata ─────────────────────────────────────


def accounts_segment_metas(
    accounts_path: str,
    *,
    program_id_override: str | None = None,
    payer_override: str | None = None,
    load_accounts_fn: Any | None = None,
    parse_segments_fn: Any | None = None,
    resolve_accounts_path_fn: Any | None = None,
    validate_vm_authority_binding_fn: Any | None = None,
    resolve_authority_pubkey_fn: Any | None = None,
    resolve_pubkey_fn: Any | None = None,
    parse_vm_seed_fn: Any | None = None,
    parse_vm_entry_fn: Any | None = None,
    segment_kind_code_fn: Any | None = None,
    derive_vm_pda_fn: Any | None = None,
    derive_segment_pda_fn: Any | None = None,
) -> tuple[dict[str, str | None], list[str]]:
    if load_accounts_fn is None:
        load_accounts_fn = load_accounts
    if parse_segments_fn is None:
        parse_segments_fn = parse_segments
    if resolve_accounts_path_fn is None:
        resolve_accounts_path_fn = resolve_accounts_path
    if validate_vm_authority_binding_fn is None:
        validate_vm_authority_binding_fn = validate_vm_authority_binding
    if resolve_authority_pubkey_fn is None:
        resolve_authority_pubkey_fn = resolve_authority_pubkey
    if resolve_pubkey_fn is None:
        resolve_pubkey_fn = resolve_pubkey
    if parse_vm_seed_fn is None:
        parse_vm_seed_fn = parse_vm_seed
    if parse_vm_entry_fn is None:
        parse_vm_entry_fn = parse_vm_entry
    if segment_kind_code_fn is None:
        segment_kind_code_fn = segment_kind_code
    if derive_vm_pda_fn is None:
        derive_vm_pda_fn = derive_vm_pda
    if derive_segment_pda_fn is None:
        derive_segment_pda_fn = derive_segment_pda

    accounts = load_accounts_fn(accounts_path)
    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    validate_vm_authority_binding_fn(accounts_path, vm)
    program_id = program_id_override or (
        cluster.get("program_id") if isinstance(cluster.get("program_id"), str) else DEFAULT_PROGRAM_ID
    )
    payer_keypair = payer_override
    if not payer_keypair and isinstance(cluster.get("payer"), str):
        payer_keypair = resolve_accounts_path_fn(accounts_path, cluster["payer"])
    authority_override = payer_keypair
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        authority_override = resolve_accounts_path_fn(accounts_path, vm["authority_keypair"])

    vm_seed = parse_vm_seed_fn(vm)
    vm_entry_pc = parse_vm_entry_fn(vm)
    authority_pubkey = resolve_authority_pubkey_fn(accounts, authority_keypair_override=authority_override)
    vm_pubkey = resolve_pubkey_fn(vm)
    if vm_seed is not None:
        if not authority_pubkey:
            raise ValueError("Unable to derive VM PDA: missing authority pubkey")
        expected_vm_pda = derive_vm_pda_fn(program_id, authority_pubkey, vm_seed)
        if vm_pubkey and vm_pubkey != expected_vm_pda:
            raise ValueError(
                "vm.pubkey does not match derived VM PDA for vm.seed/authority; "
                "remove vm.pubkey or fix vm.seed/authority"
            )
        vm_pubkey = expected_vm_pda
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey/keypair (or vm.seed + authority)")

    segments = parse_segments_fn(accounts)
    if not segments:
        raise ValueError("accounts file has no segments")

    mapped: list[tuple[int, bool, str]] = []
    for seg in segments:
        pubkey = seg.pubkey or (
            resolve_pubkey_fn({"keypair": resolve_accounts_path_fn(accounts_path, seg.keypair)})
            if seg.keypair
            else None
        )
        if vm_seed is not None:
            kind_code = segment_kind_code_fn(seg.kind)
            if kind_code is None:
                raise ValueError(
                    f"Unable to derive segment {seg.index}: unsupported kind '{seg.kind}' (expected weights|ram)"
                )
            if seg.slot == 1 and kind_code != 1:
                raise ValueError("PDA mode requires a weights segment at slot 1")
            if kind_code == 1 and seg.slot != 1:
                raise ValueError("PDA mode supports weights only at slot 1")
            if not (1 <= seg.slot <= 15):
                raise ValueError(
                    f"Unable to derive segment {seg.index}: slot {seg.slot} is out of range (1..15)"
                )
            expected_segment_pda = derive_segment_pda_fn(
                program_id,
                authority_pubkey,
                vm_seed,
                kind_code,
                seg.slot,
            )
            if pubkey and pubkey != expected_segment_pda:
                raise ValueError(
                    f"segment {seg.index} pubkey does not match derived PDA for vm.seed/authority/slot; "
                    "remove segment pubkey/keypair or fix metadata"
                )
            pubkey = expected_segment_pda
            expected_writable = kind_code == 2
            if seg.writable != expected_writable:
                access_mode = "writable" if expected_writable else "readonly"
                raise ValueError(
                    f"segment {seg.index} ({seg.kind}) must be {access_mode} in PDA mode; "
                    "fix segment writable metadata"
                )
        if not pubkey:
            raise ValueError(f"segment {seg.index} missing pubkey/keypair (or derivation metadata)")
        sort_key = seg.slot if vm_seed is not None else seg.index
        mapped.append((sort_key, seg.writable, pubkey))
    mapped.sort(key=lambda item: item[0])
    if vm_seed is not None:
        seen_slots: set[int] = set()
        for slot, _, _ in mapped:
            if slot in seen_slots:
                raise ValueError(
                    f"duplicate segment slot {slot} in PDA mode; each mapped account must use a unique slot"
                )
            seen_slots.add(slot)
        for expected_slot, (actual_slot, _, _) in enumerate(mapped, start=1):
            if actual_slot != expected_slot:
                raise ValueError(
                    "PDA execute requires contiguous segment slots starting at 1; "
                    f"missing slot {expected_slot} before configured slot {actual_slot}"
                )

    return {
        "rpc_url": cluster.get("rpc_url"),
        "program_id": program_id,
        "payer": payer_keypair or cluster.get("payer"),
        "vm_pubkey": vm_pubkey,
        "authority_pubkey": authority_pubkey,
        "vm_seed": str(vm_seed) if vm_seed is not None else None,
        "vm_entry": str(vm_entry_pc) if vm_entry_pc is not None else None,
    }, [f"{'rw' if writable else 'ro'}:{pubkey}" for _, writable, pubkey in mapped]


# ── Seeded runner args ─────────────────────────────────────────────


def append_seeded_runner_args(
    cmd: list[str],
    accounts_path: str,
    info: dict[str, str | None],
    *,
    payer_keypair: str | None,
    load_accounts_fn: Any | None = None,
    resolve_accounts_path_fn: Any | None = None,
    resolve_pubkey_fn: Any | None = None,
) -> None:
    if load_accounts_fn is None:
        load_accounts_fn = load_accounts
    if resolve_accounts_path_fn is None:
        resolve_accounts_path_fn = resolve_accounts_path
    if resolve_pubkey_fn is None:
        resolve_pubkey_fn = resolve_pubkey

    vm_seed = info.get("vm_seed")
    if not isinstance(vm_seed, str) or not vm_seed:
        return

    cmd.extend(["--vm-seed", vm_seed])

    accounts = load_accounts_fn(accounts_path)
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    authority_keypair = vm.get("authority_keypair")
    if isinstance(authority_keypair, str) and authority_keypair:
        cmd.extend(["--authority-keypair", resolve_accounts_path_fn(accounts_path, authority_keypair)])
        return

    authority = vm.get("authority")
    if isinstance(authority, str) and authority and payer_keypair:
        payer_pubkey = resolve_pubkey_fn({"keypair": payer_keypair})
        if payer_pubkey and payer_pubkey != authority:
            raise ValueError(
                "seeded run requires vm.authority_keypair when vm.authority differs from payer signer"
            )


# ── Signature extraction ──────────────────────────────────────────


def extract_last_execute_signature(output: str) -> str | None:
    matches = EXEC_SIG_RE.findall(output)
    if not matches:
        return None
    return matches[-1]


# ── Upload validation ──────────────────────────────────────────────


def validate_upload_inputs(
    file_path: str | None,
    all_pattern: str | None,
    allow_raw: bool = False,
) -> None:
    if allow_raw:
        return

    if file_path:
        suffix = Path(file_path).suffix.lower()
        if suffix in SOURCE_UPLOAD_SUFFIXES:
            raise ValueError(
                "upload expects a binary payload (for example weights.bin). "
                "Convert first with `cauldron convert ... --pack`, then upload weights.bin. "
                "Pass --allow-raw-upload to bypass this guard."
            )

    if all_pattern:
        suffix = Path(all_pattern).suffix.lower()
        if suffix in SOURCE_UPLOAD_SUFFIXES:
            raise ValueError(
                "upload --all pattern appears to target source-format files. "
                "Chunk/upload binary payloads instead. Pass --allow-raw-upload to bypass this guard."
            )
