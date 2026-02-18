import argparse
import base64
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

VM_HEADER_SIZE = 552
MMU_VM_HEADER_SIZE = VM_HEADER_SIZE
VM_ACCOUNT_SIZE_MIN = 262_696
EXECUTE_OP = 2
EXECUTE_V3_OP = 43
SEGMENT_KIND_WEIGHTS = 1
SEGMENT_KIND_RAM = 2


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def load_keypair(path: Path) -> Keypair:
    raw = json.loads(path.read_text())
    return Keypair.from_bytes(bytes(raw))


def read_u32_le(buf: bytes, offset: int) -> int:
    return int.from_bytes(buf[offset : offset + 4], "little")


def decode_i32(buf: bytes) -> list[int]:
    out = []
    for i in range(0, len(buf), 4):
        if i + 4 > len(buf):
            break
        out.append(int.from_bytes(buf[i : i + 4], "little", signed=True))
    return out


def resolve_accounts_path(accounts_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return expanded
    return (accounts_path.parent / expanded).resolve()


def parse_vm_seed(vm_entry: dict) -> int | None:
    raw = vm_entry.get("seed")
    if raw is None:
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        value = int(text, 0)
    else:
        raise ValueError("vm.seed must be an integer or string")
    if value < 0 or value > (2**64 - 1):
        raise ValueError("vm.seed must be within u64 range")
    return value


def segment_kind_code(kind: str | None) -> int | None:
    value = (kind or "").strip().lower()
    if value == "weights":
        return SEGMENT_KIND_WEIGHTS
    if value == "ram":
        return SEGMENT_KIND_RAM
    return None


def vm_seed_string(vm_seed: int) -> str:
    return f"fbv1:vm:{vm_seed:016x}"


def segment_seed_string(vm_seed: int, kind: int, slot: int) -> str:
    return f"fbv1:sg:{vm_seed:016x}:{kind:02x}{slot:02x}"


def normalize_pda_segments(
    segments: list[dict],
    *,
    vm_seed: int,
    authority_pubkey: Pubkey,
    program_pubkey: Pubkey,
) -> list[dict]:
    normalized: list[dict] = []
    for idx, seg in enumerate(segments, start=1):
        configured_pubkey = seg.get("pubkey")
        if "pubkey" in seg and not (isinstance(configured_pubkey, str) and configured_pubkey):
            raise ValueError(f"segment {idx} pubkey must be a base58 string when provided")
        kind_code = segment_kind_code(seg.get("kind") if isinstance(seg.get("kind"), str) else None)
        if kind_code is None:
            raise ValueError(
                f"segment {idx} has unsupported kind '{seg.get('kind')}' (expected weights|ram)"
            )
        slot_raw = seg.get("slot", seg.get("index", idx))
        slot = int(slot_raw)
        if slot < 1 or slot > 15:
            raise ValueError(f"segment {idx} has invalid slot {slot} (expected 1..15)")
        expected_writable = kind_code == SEGMENT_KIND_RAM
        if bool(seg.get("writable", False)) != expected_writable:
            access_mode = "writable" if expected_writable else "readonly"
            raise ValueError(
                f"segment {idx} ({seg.get('kind')}) must be {access_mode} in deterministic account mode"
            )
        expected_pubkey = Pubkey.create_with_seed(
            authority_pubkey,
            segment_seed_string(vm_seed, kind_code, slot),
            program_pubkey,
        )
        if isinstance(configured_pubkey, str) and configured_pubkey:
            if str(expected_pubkey) != configured_pubkey:
                raise ValueError(
                    f"segment {idx} pubkey does not match deterministic derived address for "
                    "vm.seed/authority/slot; remove segment pubkey or fix metadata"
                )
        normalized.append(
            {
                "pubkey": str(expected_pubkey),
                "slot": slot,
                "kind_code": kind_code,
                "writable": expected_writable,
            }
        )

    if not normalized:
        raise ValueError("deterministic execute requires at least one mapped segment")
    normalized.sort(key=lambda entry: entry["slot"])
    for idx, seg in enumerate(normalized, start=1):
        if idx > 1 and normalized[idx - 2]["slot"] == seg["slot"]:
            raise ValueError(f"duplicate segment slot {seg['slot']} in deterministic account mode")
        if seg["slot"] != idx:
            raise ValueError(
                "deterministic execute requires contiguous slots starting at 1; "
                f"missing slot {idx} before slot {seg['slot']}"
            )
    if normalized[0]["kind_code"] != SEGMENT_KIND_WEIGHTS:
        raise ValueError("deterministic execute requires a weights segment at slot 1")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--instructions", type=int, default=50000)
    parser.add_argument("--rpc-url")
    parser.add_argument("--program-id")
    parser.add_argument("--payer")
    parser.add_argument("--authority-keypair")
    parser.add_argument("--use-max", action="store_true")
    args = parser.parse_args()

    accounts_path = Path(args.accounts)
    accounts = load_toml(accounts_path)
    manifest = load_toml(Path(args.manifest))

    rpc_url = args.rpc_url or accounts.get("cluster", {}).get("rpc_url") or "http://127.0.0.1:8899"
    program_id = args.program_id or accounts.get("cluster", {}).get("program_id")
    payer_path = args.payer or accounts.get("cluster", {}).get("payer")
    if not program_id or not payer_path:
        raise SystemExit("Missing program_id/payer in accounts file")

    payer = load_keypair(Path(payer_path))
    client = Client(rpc_url)
    program_pubkey = Pubkey.from_string(program_id)
    vm_entry = accounts.get("vm", {}) if isinstance(accounts.get("vm"), dict) else {}
    vm_seed = parse_vm_seed(vm_entry)

    authority_path = resolve_accounts_path(
        accounts_path,
        args.authority_keypair
        or (vm_entry.get("authority_keypair") if isinstance(vm_entry.get("authority_keypair"), str) else None),
    )
    authority = load_keypair(authority_path) if authority_path is not None else payer
    authority_pubkey = vm_entry.get("authority") if isinstance(vm_entry.get("authority"), str) else None
    if vm_seed is not None and authority_pubkey and str(authority.pubkey()) != authority_pubkey:
        raise ValueError(
            "authority signer pubkey does not match vm.authority; "
            "provide matching --authority-keypair or update accounts file"
        )
    authority_for_derivation = (
        Pubkey.from_string(authority_pubkey) if authority_pubkey else authority.pubkey()
    )
    configured_vm_pubkey = vm_entry.get("pubkey") if isinstance(vm_entry.get("pubkey"), str) else None
    if vm_seed is not None:
        derived_vm_pubkey = Pubkey.create_with_seed(
            authority_for_derivation,
            vm_seed_string(vm_seed),
            program_pubkey,
        )
        if configured_vm_pubkey and configured_vm_pubkey != str(derived_vm_pubkey):
            raise ValueError(
                "vm.pubkey does not match deterministic derived VM address for vm.seed/authority; "
                "remove vm.pubkey or fix metadata"
            )
        vm_pubkey = str(derived_vm_pubkey)
    else:
        vm_pubkey = configured_vm_pubkey
    if not vm_pubkey:
        raise SystemExit("Missing vm.pubkey (or vm.seed + authority) in accounts file")

    metas = [
        AccountMeta(authority.pubkey() if vm_seed is not None else payer.pubkey(), True, False),
        AccountMeta(Pubkey.from_string(vm_pubkey), False, True),
    ]

    if vm_seed is not None:
        segments = normalize_pda_segments(
            accounts.get("segments", []),
            vm_seed=vm_seed,
            authority_pubkey=authority_for_derivation,
            program_pubkey=program_pubkey,
        )
        if len(segments) > 15:
            raise ValueError("deterministic execute supports at most 15 mapped segments")
        mapped_kinds = bytearray()
        for seg in segments:
            metas.append(AccountMeta(Pubkey.from_string(seg["pubkey"]), False, bool(seg["writable"])))
            mapped_kinds.append(int(seg["kind_code"]))
        data = (
            bytes([EXECUTE_V3_OP])
            + vm_seed.to_bytes(8, "little")
            + args.instructions.to_bytes(8, "little")
            + bytes([0, len(segments)])
            + bytes(mapped_kinds)
        )
    else:
        segments = sorted(accounts.get("segments", []), key=lambda s: s.get("index", 0))
        for seg in segments:
            pubkey = seg.get("pubkey")
            if not pubkey:
                continue
            metas.append(AccountMeta(Pubkey.from_string(pubkey), False, bool(seg.get("writable", False))))
        data = bytes([EXECUTE_OP]) + args.instructions.to_bytes(8, "little")

    ix = Instruction(Pubkey.from_string(program_id), data, metas)
    tx = Transaction.new_with_payer([set_compute_unit_limit(1_400_000), ix], payer.pubkey())
    blockhash = client.get_latest_blockhash().value.blockhash
    signers = [payer]
    if authority.pubkey() != payer.pubkey():
        signers.append(authority)
    tx.sign(signers, blockhash)
    sig = client.send_raw_transaction(
        tx.serialize(),
        opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed"),
    ).value
    client.confirm_transaction(sig, commitment="confirmed")

    info = client.get_account_info(Pubkey.from_string(vm_pubkey), encoding="base64").value
    if info is None:
        raise SystemExit("VM account not found")
    raw = base64.b64decode(info.data[0])
    if len(raw) < VM_ACCOUNT_SIZE_MIN:
        raise SystemExit(
            f"VM account too small ({len(raw)} bytes); expected at least {VM_ACCOUNT_SIZE_MIN}"
        )
    scratch = raw[MMU_VM_HEADER_SIZE:]
    control_offset = manifest.get("abi", {}).get("control_offset", 0)
    output_offset = manifest.get("abi", {}).get("output_offset", 0)
    output_max = manifest.get("abi", {}).get("output_max", 0)

    status = read_u32_le(scratch, control_offset + 12)
    output_len = read_u32_le(scratch, control_offset + 28)
    if output_len == 0 and args.use_max:
        output_len = output_max
    output = scratch[output_offset : output_offset + output_len]

    print("Status:", status)
    if output:
        print("Output (i32):", decode_i32(output))
    else:
        print("Output: <empty>")


if __name__ == "__main__":
    main()
