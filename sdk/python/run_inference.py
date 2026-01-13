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

MMU_VM_HEADER_SIZE = 545
EXECUTE_OP = 2


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--accounts", required=True)
    parser.add_argument("--instructions", type=int, default=50000)
    parser.add_argument("--rpc-url")
    parser.add_argument("--program-id")
    parser.add_argument("--payer")
    parser.add_argument("--use-max", action="store_true")
    args = parser.parse_args()

    accounts = load_toml(Path(args.accounts))
    manifest = load_toml(Path(args.manifest))

    rpc_url = args.rpc_url or accounts.get("cluster", {}).get("rpc_url") or "http://127.0.0.1:8899"
    program_id = args.program_id or accounts.get("cluster", {}).get("program_id")
    vm_pubkey = accounts.get("vm", {}).get("pubkey")
    payer_path = args.payer or accounts.get("cluster", {}).get("payer")
    if not program_id or not vm_pubkey or not payer_path:
        raise SystemExit("Missing program_id/vm.pubkey/payer in accounts file")

    payer = load_keypair(Path(payer_path))
    client = Client(rpc_url)

    metas = [
        AccountMeta(payer.pubkey(), True, False),
        AccountMeta(Pubkey.from_string(vm_pubkey), False, True),
    ]
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
    tx.sign([payer], blockhash)
    sig = client.send_raw_transaction(
        tx.serialize(),
        opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed"),
    ).value
    client.confirm_transaction(sig, commitment="confirmed")

    info = client.get_account_info(Pubkey.from_string(vm_pubkey), encoding="base64").value
    if info is None:
        raise SystemExit("VM account not found")
    raw = base64.b64decode(info.data[0])
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
