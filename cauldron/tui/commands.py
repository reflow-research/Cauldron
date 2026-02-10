"""Commands API — argparse-free interface to Cauldron business logic.

Every function accepts explicit kwargs and returns a CommandResult.
Subprocess operations accept an optional on_progress callback.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..manifest import load_manifest
from ..validate import validate_manifest
from ..pack import pack_manifest
from ..chunk import chunk_manifest, chunk_file
from ..schema import schema_hash32, format_hash32, update_manifest_schema_hash
from ..accounts import (
    derive_vm_pda,
    load_accounts,
    parse_segments,
    resolve_authority_pubkey,
    write_accounts,
)
from ..constants import DEFAULT_PROGRAM_ID
from ..helpers import (
    apply_accounts_env,
    append_seeded_runner_args,
    build_upload_env,
    extract_last_execute_signature,
    load_solana_cli_config,
    resolve_run_onchain,
    accounts_segment_metas,
    build_control_block,
    decode_output,
    fetch_account_data,
    parse_control_block,
    schema_output_info,
    validate_vm_authority_binding,
    wait_for_signature_slot,
    write_account,
    rpc_request_raw,
)
from .registry import list_projects
from .runtime import resolve_runtime_context

ProgressCallback = Callable[[str, float | None], None]

TEMPLATES = [
    "linear", "softmax", "naive_bayes", "two_tower",
    "mlp", "mlp2", "mlp3", "cnn1d", "tiny_cnn", "tree", "custom",
]


@dataclass
class CommandResult:
    """Universal return type for all TUI commands."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


def _blob_updates_to_dicts(updates: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for update in updates:
        out.append(
            {
                "name": getattr(update, "name", None),
                "file": getattr(update, "file", None),
                "hash": getattr(update, "hash", None),
                "size_bytes": getattr(update, "size_bytes", None),
            }
        )
    return out


def _resolve_weights_output_path(manifest_path: Path) -> Path:
    manifest = load_manifest(manifest_path)
    weights = manifest.get("weights")
    if isinstance(weights, dict):
        blobs = weights.get("blobs")
        if isinstance(blobs, list) and blobs:
            blob = blobs[0]
            if isinstance(blob, dict):
                file_name = blob.get("file")
                if isinstance(file_name, str) and file_name:
                    return manifest_path.parent / file_name
    return manifest_path.parent / "weights.bin"


def _flatten_chunk_results(results: list[Any]) -> tuple[list[str], list[dict[str, Any]]]:
    chunk_paths: list[str] = []
    summary: list[dict[str, Any]] = []
    for result in results:
        source = getattr(result, "source", None)
        chunks = getattr(result, "chunks", None)
        source_str = str(source) if source is not None else "?"
        chunk_list: list[str] = []
        if isinstance(chunks, list):
            chunk_list = [str(chunk) for chunk in chunks]
            chunk_paths.extend(chunk_list)
        summary.append(
            {
                "source": source_str,
                "chunk_count": len(chunk_list),
                "chunks": chunk_list,
            }
        )
    return chunk_paths, summary


def _parse_label_col(label_col: str | int | None) -> str | int | None:
    if not isinstance(label_col, str):
        return label_col
    stripped = label_col.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return stripped


def _normalize_decoded_output(decoded: str) -> Any:
    try:
        return json.loads(decoded)
    except Exception:
        return decoded


def _normalize_rpc_url(url: str | None) -> str:
    if isinstance(url, str):
        cleaned = url.strip().rstrip("/")
        if cleaned:
            return cleaned
    return "<unspecified-rpc>"


def _resolve_project_accounts_path(project: Any) -> Path | None:
    accounts_path = getattr(project, "accounts_path", None)
    if not isinstance(accounts_path, Path):
        return None
    if accounts_path.is_absolute():
        return accounts_path
    project_path = getattr(project, "path", None)
    if isinstance(project_path, Path):
        return project_path / accounts_path
    return accounts_path


@dataclass(frozen=True)
class _SeedFingerprint:
    rpc_url: str
    program_id: str
    authority_pubkey: str
    vm_seed: str
    vm_pubkey: str


def _build_seed_fingerprint_from_values(
    *,
    vm_seed: int,
    program_id: str,
    authority_pubkey: str,
    rpc_url: str | None,
) -> _SeedFingerprint:
    return _SeedFingerprint(
        rpc_url=_normalize_rpc_url(rpc_url),
        program_id=program_id,
        authority_pubkey=authority_pubkey,
        vm_seed=str(vm_seed),
        vm_pubkey=derive_vm_pda(program_id, authority_pubkey, vm_seed),
    )


def _build_seed_fingerprint_from_accounts(
    accounts_path: Path,
    *,
    rpc_url: str | None = None,
    program_id: str | None = None,
    payer: str | None = None,
) -> _SeedFingerprint | None:
    info, _ = accounts_segment_metas(
        str(accounts_path),
        program_id_override=program_id,
        payer_override=payer,
    )
    vm_seed = info.get("vm_seed")
    authority_pubkey = info.get("authority_pubkey")
    vm_pubkey = info.get("vm_pubkey")
    effective_program_id = program_id or info.get("program_id")
    if not (
        isinstance(vm_seed, str)
        and vm_seed
        and isinstance(authority_pubkey, str)
        and authority_pubkey
        and isinstance(vm_pubkey, str)
        and vm_pubkey
        and isinstance(effective_program_id, str)
        and effective_program_id
    ):
        return None
    return _SeedFingerprint(
        rpc_url=_normalize_rpc_url(rpc_url or info.get("rpc_url")),
        program_id=effective_program_id,
        authority_pubkey=authority_pubkey,
        vm_seed=vm_seed,
        vm_pubkey=vm_pubkey,
    )


def _find_seed_collision_for_fingerprint(
    *,
    current_fp: _SeedFingerprint,
    project_path: Path | None = None,
) -> tuple[Any, _SeedFingerprint] | None:
    current_project_path = project_path.resolve() if isinstance(project_path, Path) else None

    for project in list_projects():
        other_project_path = getattr(project, "path", None)
        if isinstance(other_project_path, Path):
            if current_project_path and other_project_path.resolve() == current_project_path:
                continue
        other_accounts_path = _resolve_project_accounts_path(project)
        if not isinstance(other_accounts_path, Path) or not other_accounts_path.exists():
            continue
        try:
            context = resolve_runtime_context(project)
            other_fp = _build_seed_fingerprint_from_accounts(
                other_accounts_path,
                rpc_url=context.rpc_url,
                program_id=context.program_id,
                payer=context.payer,
            )
        except Exception:
            continue
        if other_fp is None:
            continue
        if (
            other_fp.rpc_url == current_fp.rpc_url
            and other_fp.program_id == current_fp.program_id
            and other_fp.authority_pubkey == current_fp.authority_pubkey
            and other_fp.vm_seed == current_fp.vm_seed
        ):
            return project, other_fp
    return None


def _detect_seed_collision(
    *,
    accounts_path: Path,
    project_path: Path | None = None,
    rpc_url: str | None = None,
    program_id: str | None = None,
    payer: str | None = None,
) -> tuple[Any, _SeedFingerprint] | None:
    try:
        current_fp = _build_seed_fingerprint_from_accounts(
            accounts_path,
            rpc_url=rpc_url,
            program_id=program_id,
            payer=payer,
        )
    except Exception:
        return None
    if current_fp is None:
        return None

    return _find_seed_collision_for_fingerprint(
        current_fp=current_fp,
        project_path=project_path,
    )


def _parse_mapped_pubkeys(mapped_lines: list[str]) -> list[str]:
    pubkeys: list[str] = []
    for line in mapped_lines:
        if not isinstance(line, str) or ":" not in line:
            continue
        _, pubkey = line.split(":", 1)
        value = pubkey.strip()
        if value:
            pubkeys.append(value)
    return pubkeys


def _fetch_account_snapshot(rpc_url: str, pubkey: str) -> dict[str, Any]:
    payload = rpc_request_raw(
        rpc_url,
        "getAccountInfo",
        [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
    )
    error = payload.get("error")
    if error is not None:
        raise ValueError(f"RPC error: {error}")
    result = payload.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    if value is None:
        raise ValueError("account not found")
    if not isinstance(value, dict):
        raise ValueError("unexpected account payload")

    data = value.get("data")
    raw_data = ""
    if isinstance(data, list) and data and isinstance(data[0], str):
        raw_data = data[0]
    elif isinstance(data, str):
        raw_data = data

    try:
        decoded = base64.b64decode(raw_data, validate=False) if raw_data else b""
    except Exception as exc:
        raise ValueError(f"unable to decode account data: {exc}") from exc

    return {
        "owner": value.get("owner"),
        "lamports": value.get("lamports"),
        "data_len": len(decoded),
        "executable": bool(value.get("executable", False)),
    }


def _audit_seeded_accounts_on_chain(
    *,
    rpc_url: str | None,
    program_id: str | None,
    expected_pubkeys: list[str],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    if not isinstance(rpc_url, str) or not rpc_url.strip():
        return ["Missing RPC URL for post-create verification"], {}
    if not isinstance(program_id, str) or not program_id.strip():
        return ["Missing program ID for post-create verification"], {}
    if not expected_pubkeys:
        return ["No accounts supplied for post-create verification"], {}

    seen: set[str] = set()
    ordered_expected: list[str] = []
    for pubkey in expected_pubkeys:
        if pubkey and pubkey not in seen:
            ordered_expected.append(pubkey)
            seen.add(pubkey)

    errors: list[str] = []
    snapshots: dict[str, dict[str, Any]] = {}
    for pubkey in ordered_expected:
        try:
            snapshot = _fetch_account_snapshot(rpc_url, pubkey)
        except Exception as exc:
            errors.append(f"{pubkey}: {exc}")
            continue
        snapshots[pubkey] = snapshot

        owner = snapshot.get("owner")
        if owner != program_id:
            errors.append(f"{pubkey}: owner mismatch ({owner} != {program_id})")

        data_len = snapshot.get("data_len")
        if not isinstance(data_len, int) or data_len <= 0:
            errors.append(f"{pubkey}: empty account data")

    return errors, snapshots


# ── Validate ──────────────────────────────────────────────────────


def cmd_validate(manifest_path: Path) -> CommandResult:
    """Validate a manifest against the Frostbite spec."""
    try:
        manifest = load_manifest(manifest_path)
        errors = validate_manifest(manifest)
        if errors:
            return CommandResult(
                success=False,
                message="Validation failed",
                errors=errors,
            )
        return CommandResult(success=True, message="Manifest valid")
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Show ──────────────────────────────────────────────────────────


def cmd_show(manifest_path: Path) -> CommandResult:
    """Load and return manifest sections as structured data."""
    try:
        manifest = load_manifest(manifest_path)
        return CommandResult(
            success=True,
            message="Manifest loaded",
            data={"manifest": manifest},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Schema hash ───────────────────────────────────────────────────


def cmd_schema_hash(
    manifest_path: Path,
    update_manifest: bool = False,
) -> CommandResult:
    """Compute the schema hash for a manifest."""
    try:
        manifest = load_manifest(manifest_path)
        h = schema_hash32(manifest)
        if h is None:
            return CommandResult(success=False, message="Cannot compute schema hash for this schema type")
        formatted = format_hash32(h)
        if update_manifest:
            update_manifest_schema_hash(manifest_path, formatted)
        return CommandResult(
            success=True,
            message=f"Schema hash: {formatted}",
            data={"hash": formatted, "hash_int": h},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Init ──────────────────────────────────────────────────────────


def cmd_init(
    path: Path,
    template: str = "linear",
    manifest_name: str = "frostbite-model.toml",
    copy_guest: bool = True,
    no_weights: bool = False,
    allow_non_empty: bool = False,
) -> CommandResult:
    """Initialize a new model project.

    Delegates to the CLI init logic by importing and calling directly.
    """
    import argparse
    import io
    from contextlib import redirect_stderr, redirect_stdout
    from ..cli import _cmd_init

    args = argparse.Namespace(
        path=str(path),
        template=template,
        manifest=manifest_name,
        copy_guest=copy_guest,
        stub=not copy_guest,
        no_weights=no_weights,
        allow_non_empty=allow_non_empty,
    )
    try:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = _cmd_init(args)

        logs = [
            line
            for block in (stdout_buf.getvalue(), stderr_buf.getvalue())
            for line in block.splitlines()
            if line.strip()
        ]
        if rc == 0:
            return CommandResult(
                success=True,
                message=f"Initialized {template} project in {path}",
                data={"path": str(path), "template": template, "manifest": manifest_name},
                logs=logs,
            )
        message = logs[-1] if logs else "Init failed"
        return CommandResult(success=False, message=message, logs=logs)
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Pack ──────────────────────────────────────────────────────────


def cmd_pack(
    manifest_path: Path,
    update_size: bool = False,
    dry_run: bool = False,
    create_missing: bool = False,
) -> CommandResult:
    """Pack weights and update manifest hashes."""
    try:
        updates = pack_manifest(
            manifest_path,
            update_size=update_size,
            write=not dry_run,
            create_missing=create_missing,
        )
        return CommandResult(
            success=True,
            message="Pack complete" if not dry_run else "Pack dry-run complete",
            data={"updates": _blob_updates_to_dicts(updates)},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Convert ───────────────────────────────────────────────────────


def cmd_convert(
    manifest_path: Path,
    input_path: Path,
    template: str | None = None,
    output_path: Path | None = None,
    scale_q16: int | None = None,
    w1_scale_q16: int | None = None,
    w2_scale_q16: int | None = None,
    w3_scale_q16: int | None = None,
    w4_scale_q16: int | None = None,
    input_dim: int | None = None,
    output_dim: int | None = None,
    hidden_dim: int | None = None,
    hidden_dim1: int | None = None,
    hidden_dim2: int | None = None,
    hidden_dim3: int | None = None,
    input_dim_a: int | None = None,
    input_dim_b: int | None = None,
    embed_dim: int | None = None,
    tree_count: int | None = None,
    tree_node_count: int | None = None,
    no_bias: bool = False,
    keymap: dict[str, str] | None = None,
    no_update_manifest: bool = False,
    auto_pack: bool = False,
) -> CommandResult:
    """Convert weights to Frostbite binary format."""
    from ..convert import load_and_convert

    try:
        resolved_output = output_path or _resolve_weights_output_path(manifest_path)
        load_and_convert(
            manifest_path=manifest_path,
            input_path=input_path,
            output_path=resolved_output,
            template=template,
            scale_q16=scale_q16,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            w3_scale_q16=w3_scale_q16,
            w4_scale_q16=w4_scale_q16,
            update_manifest=not no_update_manifest,
            input_dim_override=input_dim,
            output_dim_override=output_dim,
            hidden_dim_override=hidden_dim,
            hidden_dim1_override=hidden_dim1,
            hidden_dim2_override=hidden_dim2,
            hidden_dim3_override=hidden_dim3,
            bias=not no_bias,
            keymap=keymap,
            input_dim_a_override=input_dim_a,
            input_dim_b_override=input_dim_b,
            embed_dim_override=embed_dim,
            tree_count_override=tree_count,
            tree_node_count_override=tree_node_count,
        )
        logs = [f"Converted weights: {input_path} -> {resolved_output}"]
        if auto_pack:
            pack_manifest(
                manifest_path=manifest_path,
                update_size=True,
                write=True,
                create_missing=False,
            )
            logs.append("Packed manifest")
        return CommandResult(
            success=True,
            message="Convert complete",
            data={"output": str(resolved_output)},
            logs=logs,
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Build guest ───────────────────────────────────────────────────


def cmd_build_guest(
    manifest_path: Path,
    guest_dir: Path | None = None,
    template: str | None = None,
    schema_hash_mode: str = "auto",
    target: str = "riscv64imac-unknown-none-elf",
    release: bool = True,
) -> CommandResult:
    """Configure and compile the RISC-V guest program."""
    from ..guest import write_guest_config, build_guest

    try:
        manifest = load_manifest(manifest_path)
        errors = validate_manifest(manifest)
        if errors:
            return CommandResult(success=False, message="Manifest validation failed", errors=errors)

        effective_guest = guest_dir or manifest_path.parent / "guest"
        cfg_path = write_guest_config(
            manifest_path=manifest_path,
            guest_dir=effective_guest,
            template=template,
            schema_hash_mode=schema_hash_mode,
        )
        rc = build_guest(
            guest_dir=effective_guest,
            target=target,
            release=release,
        )
        if rc != 0:
            return CommandResult(
                success=False,
                message=f"Guest build failed (rc={rc})",
                data={"guest_dir": str(effective_guest), "target": target, "config": str(cfg_path)},
            )
        return CommandResult(
            success=True,
            message="Guest build complete",
            data={"guest_dir": str(effective_guest), "target": target, "config": str(cfg_path)},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Chunk ─────────────────────────────────────────────────────────


def cmd_chunk(
    manifest_path: Path | None = None,
    file_path: Path | None = None,
    chunk_size: int | None = None,
    out_dir: Path | None = None,
) -> CommandResult:
    """Split weights into uploadable chunks."""
    try:
        if manifest_path:
            results = chunk_manifest(manifest_path, chunk_size, out_dir)
        elif file_path and chunk_size:
            effective_out_dir = out_dir or file_path.resolve().parent
            results = [chunk_file(file_path, chunk_size, effective_out_dir)]
        else:
            return CommandResult(success=False, message="Provide --manifest or --file + --chunk-size")
        flat_chunks, summary = _flatten_chunk_results(results)
        return CommandResult(
            success=True,
            message="Chunk complete",
            data={"chunks": flat_chunks, "results": summary},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Accounts show ─────────────────────────────────────────────────


def cmd_accounts_show(accounts_path: Path) -> CommandResult:
    """Display account mapping and derived PDA pubkeys."""
    try:
        info, mapped_lines = accounts_segment_metas(str(accounts_path))
        return CommandResult(
            success=True,
            message="Accounts loaded",
            data={
                "info": info,
                "mapped": mapped_lines,
            },
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Output (read from chain) ─────────────────────────────────────


def cmd_output(
    manifest_path: Path,
    accounts_path: Path,
    rpc_url: str | None = None,
    after_signature: str | None = None,
    commitment: str = "confirmed",
    wait_seconds: float = 30.0,
    poll_interval: float = 0.5,
    output_format: str = "auto",
    use_max: bool = False,
) -> CommandResult:
    """Read model inference output from VM scratch memory."""
    try:
        manifest = load_manifest(manifest_path)
        abi = manifest.get("abi")
        if not isinstance(abi, dict):
            return CommandResult(success=False, message="Manifest missing abi table")
        control_offset = abi.get("control_offset")
        output_offset = abi.get("output_offset")
        output_max = abi.get("output_max")
        if not isinstance(control_offset, int):
            return CommandResult(success=False, message="abi.control_offset must be an integer")
        if not isinstance(output_offset, int):
            return CommandResult(success=False, message="abi.output_offset must be an integer")
        if not isinstance(output_max, int):
            return CommandResult(success=False, message="abi.output_max must be an integer")

        info, _ = accounts_segment_metas(str(accounts_path))
        effective_rpc = rpc_url or info.get("rpc_url") or "http://127.0.0.1:8899"
        if not isinstance(effective_rpc, str):
            return CommandResult(success=False, message="Invalid rpc_url")
        vm_pubkey = info.get("vm_pubkey")
        if not isinstance(vm_pubkey, str):
            return CommandResult(success=False, message="Accounts file missing vm pubkey")

        min_context_slot = None
        if after_signature:
            slot = wait_for_signature_slot(
                effective_rpc, after_signature, commitment, wait_seconds, poll_interval,
            )
            min_context_slot = slot

        from ..constants import MMU_VM_HEADER_SIZE

        raw = fetch_account_data(
            effective_rpc, vm_pubkey,
            commitment=commitment,
            min_context_slot=min_context_slot,
            wait_seconds=wait_seconds,
            poll_interval=poll_interval,
        )
        if len(raw) < MMU_VM_HEADER_SIZE:
            return CommandResult(success=False, message="VM account data too small")
        scratch = raw[MMU_VM_HEADER_SIZE:]
        cb = parse_control_block(scratch, control_offset)
        output_len = cb.get("output_len", 0)
        if output_len == 0 and use_max:
            output_len = output_max

        out_dtype, out_count = schema_output_info(manifest)
        fmt = output_format
        if fmt == "auto":
            fmt = out_dtype or "hex"

        out_start = output_offset
        out_end = output_offset + output_len
        if out_end > len(scratch):
            return CommandResult(success=False, message="Output buffer out of bounds")
        output_bytes = scratch[out_start:out_end]
        decoded = decode_output(output_bytes, fmt, out_count)
        parsed_output = decoded if fmt in {"hex", "raw"} else _normalize_decoded_output(decoded)

        return CommandResult(
            success=True,
            message="Output read",
            data={
                "rpc_url": effective_rpc,
                "vm": vm_pubkey,
                "status": cb.get("status", -1),
                "output_len": output_len,
                "output_format": fmt,
                "output": parsed_output,
                "output_raw": decoded,
                "input_ptr": cb.get("input_ptr"),
                "output_ptr": cb.get("output_ptr"),
            },
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Accounts init ────────────────────────────────────────────────


def cmd_accounts_init(
    manifest_path: Path | None = None,
    out_path: Path | None = None,
    rpc_url: str | None = None,
    program_id: str | None = None,
    payer: str | None = None,
    vm_seed: int | None = None,
    entry_pc: int | None = None,
    ram_count: int = 1,
    ram_bytes: int = 262_144,
    project_path: Path | None = None,
    allow_seed_reuse: bool = False,
) -> CommandResult:
    """Generate accounts configuration (PDA mode)."""
    import secrets

    try:
        cfg = load_solana_cli_config()
        effective_out = out_path
        if effective_out is None:
            if manifest_path:
                effective_out = manifest_path.parent / "frostbite-accounts.toml"
            else:
                effective_out = Path("frostbite-accounts.toml")

        if ram_count > 14:
            return CommandResult(success=False, message="PDA mode supports at most 14 RAM segments")
        if ram_count < 1:
            return CommandResult(success=False, message="ram_count must be >= 1")

        # Resolve entry PC from manifest if not provided
        effective_entry_pc = entry_pc
        if effective_entry_pc is None and manifest_path:
            manifest = load_manifest(manifest_path)
            abi = manifest.get("abi") if isinstance(manifest, dict) else None
            if isinstance(abi, dict) and isinstance(abi.get("entry"), int):
                effective_entry_pc = int(abi["entry"])
        if effective_entry_pc is None:
            effective_entry_pc = 0x4000

        cluster = {
            "rpc_url": rpc_url or cfg.get("json_rpc_url"),
            "program_id": program_id or cfg.get("program_id") or DEFAULT_PROGRAM_ID,
            "payer": payer or cfg.get("keypair_path"),
        }
        vm_entry: dict[str, str | int] = {
            "seed": vm_seed if vm_seed is not None else secrets.randbits(64),
            "entry": effective_entry_pc,
            "account_model": "seeded",
        }
        segments: list[dict] = [
            {"index": 1, "slot": 1, "kind": "weights", "writable": False},
        ]
        for i in range(ram_count):
            seg: dict[str, str | bool | int] = {
                "index": i + 2,
                "slot": i + 2,
                "kind": "ram",
                "writable": True,
            }
            if ram_bytes > 0:
                seg["bytes"] = ram_bytes
            segments.append(seg)

        data = {"cluster": cluster, "vm": vm_entry, "segments": segments}
        if not allow_seed_reuse:
            candidate_project_path = project_path
            if candidate_project_path is None:
                if manifest_path:
                    candidate_project_path = manifest_path.parent
                else:
                    candidate_project_path = effective_out.parent

            candidate_seed = vm_entry.get("seed")
            candidate_program_id = cluster.get("program_id")
            payer_override = cluster.get("payer")
            try:
                authority_pubkey = resolve_authority_pubkey(
                    data,
                    authority_keypair_override=payer_override if isinstance(payer_override, str) else None,
                )
            except Exception:
                authority_pubkey = None

            if (
                isinstance(candidate_seed, int)
                and isinstance(candidate_program_id, str)
                and candidate_program_id
                and isinstance(authority_pubkey, str)
                and authority_pubkey
            ):
                collision = None
                try:
                    candidate_fp = _build_seed_fingerprint_from_values(
                        vm_seed=candidate_seed,
                        program_id=candidate_program_id,
                        authority_pubkey=authority_pubkey,
                        rpc_url=cluster.get("rpc_url"),
                    )
                    collision = _find_seed_collision_for_fingerprint(
                        current_fp=candidate_fp,
                        project_path=candidate_project_path,
                    )
                except Exception:
                    collision = None
                if collision is not None:
                    other_project, _ = collision
                    other_name = getattr(other_project, "name", "<unknown>")
                    other_path = getattr(other_project, "path", "<unknown>")
                    return CommandResult(
                        success=False,
                        message=(
                            "Seed collision blocked: vm.seed + authority + program already "
                            f"registered by project '{other_name}' at {other_path}"
                        ),
                        data={
                            "vm_seed": candidate_seed,
                            "authority_pubkey": authority_pubkey,
                            "program_id": candidate_program_id,
                            "rpc_url": cluster.get("rpc_url"),
                        },
                    )

        write_accounts(effective_out, data)
        return CommandResult(
            success=True,
            message=f"Accounts written to {effective_out}",
            data={
                "path": str(effective_out),
                "vm_seed": vm_entry["seed"],
                "rpc_url": cluster.get("rpc_url"),
                "program_id": cluster.get("program_id"),
                "payer": cluster.get("payer"),
            },
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Accounts create ──────────────────────────────────────────────


def cmd_accounts_create(
    accounts_path: Path,
    rpc_url: str | None = None,
    program_id: str | None = None,
    payer: str | None = None,
    ram_bytes: int = 262_144,
    on_progress: ProgressCallback | None = None,
    project_path: Path | None = None,
    allow_seed_reuse: bool = False,
) -> CommandResult:
    """Create on-chain accounts (PDA mode via Rust tools)."""
    import os
    import subprocess

    try:
        cfg = load_solana_cli_config()
        info, mapped_lines = accounts_segment_metas(
            str(accounts_path),
            program_id_override=program_id,
            payer_override=payer,
        )
        vm_seed = info.get("vm_seed")
        if not isinstance(vm_seed, str) or not vm_seed:
            return CommandResult(success=False, message="Accounts require vm.seed (PDA mode)")

        accounts = load_accounts(str(accounts_path))
        vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
        validate_vm_authority_binding(str(accounts_path), vm)
        segments = parse_segments(accounts)

        effective_rpc = rpc_url or info.get("rpc_url") or cfg.get("json_rpc_url")
        effective_payer = payer or info.get("payer") or cfg.get("keypair_path")
        effective_pid = program_id or info.get("program_id") or DEFAULT_PROGRAM_ID

        if not allow_seed_reuse:
            collision = _detect_seed_collision(
                accounts_path=accounts_path,
                project_path=project_path or accounts_path.parent,
                rpc_url=effective_rpc,
                program_id=effective_pid,
                payer=effective_payer if isinstance(effective_payer, str) else None,
            )
            if collision is not None:
                other_project, other_fp = collision
                other_name = getattr(other_project, "name", "<unknown>")
                other_path = getattr(other_project, "path", "<unknown>")
                return CommandResult(
                    success=False,
                    message=(
                        "Seed collision blocked: this accounts file resolves to an existing VM used "
                        f"by project '{other_name}' at {other_path}"
                    ),
                    data={
                        "vm_seed": other_fp.vm_seed,
                        "authority_pubkey": other_fp.authority_pubkey,
                        "vm_pubkey": other_fp.vm_pubkey,
                        "program_id": other_fp.program_id,
                        "rpc_url": other_fp.rpc_url,
                    },
                )

        segment_specs: list[str] = []
        created_slots: set[int] = set()
        skipped_weights_without_size = False
        for seg in segments:
            kind = seg.kind.strip().lower()
            if kind == "ram":
                payload = seg.bytes if isinstance(seg.bytes, int) and seg.bytes > 0 else ram_bytes
                segment_specs.append(f"ram:{seg.slot}:{payload}")
                created_slots.add(seg.slot)
            elif kind == "weights" and isinstance(seg.bytes, int) and seg.bytes > 0:
                segment_specs.append(f"weights:{seg.slot}:{seg.bytes}")
                created_slots.add(seg.slot)
            elif kind == "weights":
                skipped_weights_without_size = True

        env = os.environ.copy()
        if effective_rpc:
            env["FROSTBITE_RPC_URL"] = effective_rpc
        if isinstance(effective_payer, str):
            env["FROSTBITE_PAYER_KEYPAIR"] = effective_payer
        if isinstance(effective_pid, str):
            env["FROSTBITE_PROGRAM_ID"] = effective_pid
        elif "FROSTBITE_PROGRAM_ID" not in env:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

        # Authority handling
        from ..accounts import resolve_authority_pubkey
        auth_kp = vm.get("authority_keypair")
        if isinstance(auth_kp, str) and auth_kp:
            from ..helpers import resolve_accounts_path
            resolved_kp = resolve_accounts_path(str(accounts_path), auth_kp)
            env["FROSTBITE_AUTHORITY_KEYPAIR"] = resolved_kp
        authority_pubkey = resolve_authority_pubkey(
            accounts,
            authority_keypair_override=env.get("FROSTBITE_AUTHORITY_KEYPAIR") or env.get("FROSTBITE_PAYER_KEYPAIR"),
        )
        if authority_pubkey:
            env["FROSTBITE_AUTHORITY_PUBKEY"] = authority_pubkey

        rust_tools = Path(__file__).resolve().parent.parent / "rust_tools"
        cmd = ["cargo", "run", "--bin", "init_pda_accounts", "--", "--vm-seed", vm_seed]
        for spec in segment_specs:
            cmd.extend(["--segment", spec])

        if on_progress:
            on_progress(f"Running: {' '.join(cmd)}", None)
        proc = subprocess.run(cmd, env=env, cwd=str(rust_tools), capture_output=True, text=True)
        logs = []
        if proc.stdout:
            logs.extend(proc.stdout.strip().splitlines())
        if proc.stderr:
            logs.extend(proc.stderr.strip().splitlines())

        if proc.returncode == 0:
            if skipped_weights_without_size:
                logs.append(
                    "Note: weights segment has no bytes in accounts file; it will be created during upload."
                )

            mapped_pubkeys = _parse_mapped_pubkeys(mapped_lines)
            sorted_segments = sorted(segments, key=lambda seg: seg.slot)
            slot_to_pubkey: dict[int, str] = {}
            for idx, seg in enumerate(sorted_segments):
                if idx < len(mapped_pubkeys):
                    slot_to_pubkey[seg.slot] = mapped_pubkeys[idx]

            expected_pubkeys: list[str] = []
            vm_pubkey = info.get("vm_pubkey")
            if isinstance(vm_pubkey, str) and vm_pubkey:
                expected_pubkeys.append(vm_pubkey)
            for slot in sorted(created_slots):
                pubkey = slot_to_pubkey.get(slot)
                if pubkey:
                    expected_pubkeys.append(pubkey)

            verify_errors, snapshots = _audit_seeded_accounts_on_chain(
                rpc_url=effective_rpc if isinstance(effective_rpc, str) else None,
                program_id=effective_pid if isinstance(effective_pid, str) else None,
                expected_pubkeys=expected_pubkeys,
            )
            if verify_errors:
                logs.append("Post-create verification failed:")
                logs.extend(f"  {line}" for line in verify_errors)
                return CommandResult(
                    success=False,
                    message="Accounts created but verification failed on target RPC",
                    logs=logs,
                    data={
                        "rpc_url": effective_rpc,
                        "program_id": effective_pid,
                        "expected_accounts": expected_pubkeys,
                        "snapshots": snapshots,
                    },
                )

            logs.append(
                "Verified "
                f"{len(expected_pubkeys)} account(s) on "
                f"{_normalize_rpc_url(effective_rpc if isinstance(effective_rpc, str) else None)}"
            )
            return CommandResult(
                success=True,
                message="Accounts created and verified",
                logs=logs,
                data={
                    "rpc_url": effective_rpc,
                    "program_id": effective_pid,
                    "verified_accounts": expected_pubkeys,
                    "snapshots": snapshots,
                },
            )
        return CommandResult(success=False, message=f"Account creation failed (rc={proc.returncode})", logs=logs)
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Accounts close VM ────────────────────────────────────────────


def cmd_accounts_close_vm(
    accounts_path: Path,
    recipient: str | None = None,
    rpc_url: str | None = None,
    program_id: str | None = None,
    payer: str | None = None,
) -> CommandResult:
    """Close VM PDA and reclaim rent."""
    import os
    import subprocess

    from ..constants import DEFAULT_PROGRAM_ID

    try:
        info, _ = accounts_segment_metas(
            str(accounts_path),
            program_id_override=program_id,
            payer_override=payer,
        )
        vm_seed = info.get("vm_seed")
        if not isinstance(vm_seed, str) or not vm_seed:
            return CommandResult(success=False, message="close-vm requires vm.seed (PDA mode)")

        env = os.environ.copy()
        if rpc_url or info.get("rpc_url"):
            env["FROSTBITE_RPC_URL"] = rpc_url or info["rpc_url"]
        if payer or info.get("payer"):
            env["FROSTBITE_PAYER_KEYPAIR"] = payer or info["payer"]
        pid = program_id or info.get("program_id")
        if pid:
            env["FROSTBITE_PROGRAM_ID"] = pid
        elif "FROSTBITE_PROGRAM_ID" not in env:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

        env = apply_accounts_env(env, str(accounts_path), require_weights_keypair=False)

        rust_tools = Path(__file__).resolve().parent.parent / "rust_tools"
        args = ["close-vm", "--vm-seed", vm_seed]
        if recipient:
            args.extend(["--recipient", recipient])
        cmd = ["cargo", "run", "--bin", "pda_account_ops", "--", *args]

        proc = subprocess.run(cmd, env=env, cwd=str(rust_tools), capture_output=True, text=True)
        logs = []
        if proc.stdout:
            logs.extend(proc.stdout.strip().splitlines())
        if proc.stderr:
            logs.extend(proc.stderr.strip().splitlines())

        if proc.returncode == 0:
            return CommandResult(success=True, message="VM closed", logs=logs)
        return CommandResult(success=False, message=f"close-vm failed (rc={proc.returncode})", logs=logs)
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Upload ───────────────────────────────────────────────────────


def cmd_upload(
    file_path: Path | None = None,
    glob_pattern: str | None = None,
    accounts_path: Path | None = None,
    rpc_url: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> CommandResult:
    """Upload weight chunks to on-chain accounts."""
    from ..upload import upload_model_chunk, upload_all_chunks

    try:
        if not file_path and not glob_pattern:
            return CommandResult(success=False, message="Provide --file or --all glob pattern")

        env = build_upload_env(
            rpc_url=rpc_url,
            payer=payer,
            program_id=program_id,
        )
        if accounts_path:
            env = apply_accounts_env(env, str(accounts_path), require_weights_keypair=True)

        if glob_pattern:
            if on_progress:
                on_progress(f"Uploading chunks via pattern: {glob_pattern}", None)
            rc = upload_all_chunks(glob_pattern, extra_args=[], env=env)
        else:
            if on_progress:
                on_progress(f"Uploading chunk: {file_path}", None)
            rc = upload_model_chunk(file_path, extra_args=[], env=env)

        if rc == 0:
            return CommandResult(success=True, message="Upload complete")
        return CommandResult(success=False, message=f"Upload failed (rc={rc})")
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Input write ──────────────────────────────────────────────────


def cmd_input_write(
    manifest_path: Path,
    accounts_path: Path,
    data_path: Path | None = None,
    input_bin: Path | None = None,
    include_header: bool | None = None,
    include_crc: bool = False,
    schema_hash_mode: str = "auto",
    rpc_url: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
    chunk_size: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> CommandResult:
    """Write input data and control block to VM scratch memory."""
    import os
    import tempfile

    from ..constants import DEFAULT_PROGRAM_ID, MMU_VM_HEADER_SIZE
    from ..input import pack_input, load_payload_from_path

    try:
        manifest = load_manifest(str(manifest_path))

        # Resolve header inclusion
        effective_header = include_header
        if effective_header is None:
            validation = manifest.get("validation") if isinstance(manifest, dict) else None
            if isinstance(validation, dict) and validation.get("mode") == "guest":
                effective_header = True
            else:
                effective_header = False

        schema_type = None
        if isinstance(manifest.get("schema"), dict):
            schema_type = manifest["schema"].get("type")

        if input_bin:
            if schema_type != "custom":
                return CommandResult(success=False, message="--input-bin only for custom schemas")
            payload = input_bin.read_bytes()
        elif data_path:
            payload = load_payload_from_path(data_path)
        else:
            return CommandResult(success=False, message="Provide --data or --input-bin")

        payload_bytes = pack_input(
            manifest_path,
            payload,
            include_header=effective_header,
            include_crc=include_crc,
            schema_hash_mode=schema_hash_mode,
        )

        abi = manifest.get("abi") if isinstance(manifest, dict) else None
        if not isinstance(abi, dict):
            return CommandResult(success=False, message="Manifest missing abi table")

        control_offset = abi.get("control_offset", 0)
        control_size = abi.get("control_size", 64)
        input_offset = abi.get("input_offset", 4096)
        input_max = abi.get("input_max", 4096)
        output_offset = abi.get("output_offset", 8192)

        if len(payload_bytes) > input_max:
            return CommandResult(
                success=False,
                message=f"Input {len(payload_bytes)} bytes exceeds abi.input_max {input_max}",
            )

        control_bytes = build_control_block(
            control_size, input_offset, len(payload_bytes), output_offset, 0,
        )

        info, _ = accounts_segment_metas(
            str(accounts_path), program_id_override=program_id, payer_override=payer,
        )
        vm_pubkey = info.get("vm_pubkey")
        if not vm_pubkey:
            return CommandResult(success=False, message="Accounts file missing vm pubkey")

        env = os.environ.copy()
        if rpc_url or info.get("rpc_url"):
            env["FROSTBITE_RPC_URL"] = rpc_url or info["rpc_url"]
        if payer or info.get("payer"):
            env["FROSTBITE_PAYER_KEYPAIR"] = payer or info["payer"]
        pid = program_id or info.get("program_id")
        if pid:
            env["FROSTBITE_PROGRAM_ID"] = pid
        elif "FROSTBITE_PROGRAM_ID" not in env:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

        input_write_offset = MMU_VM_HEADER_SIZE + input_offset
        control_write_offset = MMU_VM_HEADER_SIZE + control_offset

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_file = tmp_path / "input.bin"
            control_file = tmp_path / "control.bin"
            input_file.write_bytes(payload_bytes)
            control_file.write_bytes(control_bytes)

            if on_progress:
                on_progress(f"Writing input ({len(payload_bytes)}B) @ 0x{input_write_offset:X}", 0.3)
            rc = write_account(env, vm_pubkey, input_write_offset, input_file, chunk_size)
            if rc != 0:
                return CommandResult(success=False, message=f"Input write failed (rc={rc})")

            if on_progress:
                on_progress(f"Writing control ({len(control_bytes)}B) @ 0x{control_write_offset:X}", 0.8)
            rc = write_account(env, vm_pubkey, control_write_offset, control_file, chunk_size)
            if rc != 0:
                return CommandResult(success=False, message=f"Control write failed (rc={rc})")

        return CommandResult(
            success=True,
            message="Input staged in VM scratch",
            data={"input_bytes": len(payload_bytes), "vm": vm_pubkey},
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Program load ─────────────────────────────────────────────────


def cmd_program_load(
    program_path: Path,
    accounts_path: Path,
    rpc_url: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
    verbose: bool = False,
    on_progress: ProgressCallback | None = None,
) -> CommandResult:
    """Load guest ELF into existing VM."""
    import os
    import subprocess

    from ..constants import DEFAULT_PROGRAM_ID

    try:
        info, _ = accounts_segment_metas(
            str(accounts_path), program_id_override=program_id, payer_override=payer,
        )
        vm_pubkey = info.get("vm_pubkey")
        if not vm_pubkey:
            return CommandResult(success=False, message="Accounts file missing vm pubkey")

        env = os.environ.copy()
        if rpc_url or info.get("rpc_url"):
            env["FROSTBITE_RPC_URL"] = rpc_url or info["rpc_url"]
        effective_payer = payer or (info.get("payer") if isinstance(info.get("payer"), str) else None)
        if effective_payer:
            env["FROSTBITE_PAYER_KEYPAIR"] = effective_payer
        pid = program_id or info.get("program_id")
        if pid:
            env["FROSTBITE_PROGRAM_ID"] = pid
        elif "FROSTBITE_PROGRAM_ID" not in env:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

        run_onchain = resolve_run_onchain()
        cmd = [run_onchain, str(program_path), "--vm", vm_pubkey, "--load", "--load-only"]
        append_seeded_runner_args(cmd, str(accounts_path), info, payer_keypair=effective_payer)

        if rpc_url or info.get("rpc_url"):
            cmd.extend(["--rpc", rpc_url or info["rpc_url"]])
        if effective_payer:
            cmd.extend(["--keypair", effective_payer])
        effective_pid = pid or DEFAULT_PROGRAM_ID
        cmd.extend(["--program-id", effective_pid])
        if verbose:
            cmd.append("--verbose")

        if on_progress:
            on_progress(f"Loading program: {program_path.name}", None)
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        logs = []
        if proc.stdout:
            logs.extend(proc.stdout.strip().splitlines())
        if proc.stderr:
            logs.extend(proc.stderr.strip().splitlines())

        if proc.returncode == 0:
            return CommandResult(success=True, message="Program loaded", logs=logs)
        return CommandResult(success=False, message=f"Program load failed (rc={proc.returncode})", logs=logs)
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Invoke ───────────────────────────────────────────────────────


def cmd_invoke(
    accounts_path: Path,
    program_path: Path | None = None,
    rpc_url: str | None = None,
    payer: str | None = None,
    program_id: str | None = None,
    mode: str = "fresh",
    entry_pc: int | None = None,
    instructions: int = 50_000,
    compute_limit: int | None = None,
    max_tx: int | None = None,
    fast: bool = False,
    no_simulate: bool = False,
    verbose: bool = False,
    on_progress: ProgressCallback | None = None,
) -> CommandResult:
    """Invoke inference on-chain."""
    import os
    import subprocess

    from ..constants import DEFAULT_PROGRAM_ID

    try:
        if fast:
            if program_path:
                return CommandResult(success=False, message="--fast cannot be combined with --program-path")
            no_simulate = True

        info, mapped_lines = accounts_segment_metas(
            str(accounts_path), program_id_override=program_id, payer_override=payer,
        )
        vm_pubkey = info.get("vm_pubkey")
        if not vm_pubkey:
            return CommandResult(success=False, message="Accounts file missing vm pubkey")

        env = os.environ.copy()
        if rpc_url or info.get("rpc_url"):
            env["FROSTBITE_RPC_URL"] = rpc_url or info["rpc_url"]
        effective_payer = payer or (info.get("payer") if isinstance(info.get("payer"), str) else None)
        if effective_payer:
            env["FROSTBITE_PAYER_KEYPAIR"] = effective_payer
        pid = program_id or info.get("program_id")
        if pid:
            env["FROSTBITE_PROGRAM_ID"] = pid
        elif "FROSTBITE_PROGRAM_ID" not in env:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

        # Write mapped accounts
        mapped_path = Path("mapped_accounts.txt")
        mapped_path.write_text("\n".join(mapped_lines) + "\n")
        has_writable = any(line.startswith("rw:") for line in mapped_lines)
        seeded_mode = isinstance(info.get("vm_seed"), str) and bool(info.get("vm_seed"))

        if mode not in {"fresh", "resume"}:
            return CommandResult(success=False, message="mode must be 'fresh' or 'resume'")

        entry_pc_value: int | None = None
        if mode == "fresh" and seeded_mode:
            if entry_pc is not None:
                entry_pc_value = entry_pc
            elif not program_path:
                vm_entry = info.get("vm_entry")
                if isinstance(vm_entry, str) and vm_entry:
                    entry_pc_value = int(vm_entry, 0)
                else:
                    return CommandResult(
                        success=False,
                        message="Fresh invoke requires entry PC; set vm.entry or pass --entry-pc",
                    )

        run_onchain = resolve_run_onchain()
        cmd = [run_onchain]
        if program_path:
            cmd.extend([str(program_path), "--load"])
        cmd.extend([
            "--vm", vm_pubkey,
            "--mapped-file", str(mapped_path),
            "--instructions", str(instructions),
        ])
        append_seeded_runner_args(cmd, str(accounts_path), info, payer_keypair=effective_payer)

        if seeded_mode:
            if mode == "resume":
                cmd.append("--resume")
            elif entry_pc_value is not None:
                cmd.extend(["--entry-pc", hex(entry_pc_value)])
        if has_writable:
            cmd.extend(["--ram-count", "0"])
        if compute_limit is not None:
            cmd.extend(["--compute-limit", str(compute_limit)])
        if max_tx is not None:
            cmd.extend(["--max-tx", str(max_tx)])
        if rpc_url or info.get("rpc_url"):
            cmd.extend(["--rpc", rpc_url or info["rpc_url"]])
        if effective_payer:
            cmd.extend(["--keypair", effective_payer])
        effective_pid = pid or DEFAULT_PROGRAM_ID
        cmd.extend(["--program-id", effective_pid])
        if no_simulate:
            cmd.append("--no-simulate")
        if verbose:
            cmd.append("--verbose")

        if on_progress:
            on_progress(f"Invoking: {' '.join(cmd[:4])}...", None)

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        output_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        logs = [line for line in output_text.strip().splitlines() if line.strip()]

        sig = extract_last_execute_signature(output_text)

        if proc.returncode == 0:
            return CommandResult(
                success=True,
                message="Invoke complete",
                data={"signature": sig, "vm": vm_pubkey},
                logs=logs,
            )
        return CommandResult(
            success=False,
            message=f"Invoke failed (rc={proc.returncode})",
            logs=logs,
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))


# ── Train ────────────────────────────────────────────────────────


def cmd_train(
    manifest_path: Path,
    data_path: Path,
    template: str | None = None,
    label_col: str | int | None = None,
    task: str = "regression",
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    val_split: float = 0.1,
    seed: int = 123,
    hidden_dim: int | None = None,
    no_bias: bool = False,
    no_convert: bool = False,
    output_dir: Path | None = None,
) -> CommandResult:
    """Train a model from data using the Cauldron training harness."""
    import argparse

    try:
        from ..training.cli import run_train_from_args

        args = argparse.Namespace(
            manifest=str(manifest_path),
            data=str(data_path),
            template=template,
            label_col=_parse_label_col(label_col),
            task=task,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            val_split=val_split,
            seed=seed,
            hidden_dim=hidden_dim,
            hidden_dim1=None,
            hidden_dim2=None,
            hidden_dim3=None,
            kernel_size=None,
            out_channels=None,
            stride=None,
            input_height=None,
            input_width=None,
            input_dim_a=None,
            input_dim_b=None,
            embed_dim=None,
            tree_max_depth=None,
            no_bias=no_bias,
            no_convert=no_convert,
            output_dir=str(output_dir) if output_dir else None,
            calibrate_percentile=None,
            input_calibrate_percentile=None,
        )
        rc = run_train_from_args(args)
        if rc == 0:
            return CommandResult(success=True, message="Training complete")
        return CommandResult(success=False, message=f"Training failed (rc={rc})")
    except ImportError:
        return CommandResult(
            success=False,
            message="Training requires torch and numpy. Install with: pip install torch numpy",
        )
    except Exception as exc:
        return CommandResult(success=False, message=str(exc))
