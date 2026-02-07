#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/cauldron-devnet-fastpath.sh [options]

Common flow wrapper:
  convert/build -> accounts init/create -> upload -> input-write -> program load -> invoke -> output

Options:
  --manifest <path>        Manifest path (default: ./frostbite-model.toml)
  --accounts <path>        Accounts file path (default: <manifest_dir>/frostbite-accounts.toml)
  --weights <path>         Optional weights source (.json/.npz/.pt/etc or .bin)
  --input <path>           Input JSON path (default: ./input.json)
  --input-bin <path>       Input blob path for custom schema (mutually exclusive with --input)
  --program <path>         Guest ELF path (default: <manifest_dir>/guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest)
  --ram-count <n>          RAM segment count for accounts init (default: 1)
  --instructions <n>       Invoke instruction slice (default: auto preset)
  --max-tx <n>             Invoke max transactions (default: auto preset)
  --rpc-url <url>          RPC URL override
  --payer <path>           Payer keypair override
  --program-id <pubkey>    Program id override
  --skip-build             Skip build-guest
  --skip-accounts          Skip accounts init/create
  --skip-upload            Skip upload step
  --skip-load              Skip program load step
  --skip-output            Skip output step
  --cleanup                Run cleanup at end (close segments + VM)
  --dry-run                Print commands without executing
  -h, --help               Show this help

Notes:
  - Auto invoke preset:
      * cnn1d/tiny_cnn -> --instructions 10000 --max-tx 120
      * other templates -> --instructions 50000 --max-tx 10
  - If --weights is omitted, convert is skipped.
  - Upload is skipped automatically when manifest has no [weights] table.
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if command -v cauldron >/dev/null 2>&1; then
  CAULDRON=(cauldron)
else
  CAULDRON=(python3 -m cauldron.cli)
fi

MANIFEST="frostbite-model.toml"
ACCOUNTS=""
WEIGHTS=""
INPUT_JSON="input.json"
INPUT_BIN=""
PROGRAM=""
RAM_COUNT=1
INSTRUCTIONS=""
MAX_TX=""
RPC_URL=""
PAYER=""
PROGRAM_ID=""
SKIP_BUILD=0
SKIP_ACCOUNTS=0
SKIP_UPLOAD=0
SKIP_LOAD=0
SKIP_OUTPUT=0
CLEANUP=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --accounts) ACCOUNTS="$2"; shift 2 ;;
    --weights) WEIGHTS="$2"; shift 2 ;;
    --input) INPUT_JSON="$2"; shift 2 ;;
    --input-bin) INPUT_BIN="$2"; shift 2 ;;
    --program) PROGRAM="$2"; shift 2 ;;
    --ram-count) RAM_COUNT="$2"; shift 2 ;;
    --instructions) INSTRUCTIONS="$2"; shift 2 ;;
    --max-tx) MAX_TX="$2"; shift 2 ;;
    --rpc-url) RPC_URL="$2"; shift 2 ;;
    --payer) PAYER="$2"; shift 2 ;;
    --program-id) PROGRAM_ID="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --skip-accounts) SKIP_ACCOUNTS=1; shift ;;
    --skip-upload) SKIP_UPLOAD=1; shift ;;
    --skip-load) SKIP_LOAD=1; shift ;;
    --skip-output) SKIP_OUTPUT=1; shift ;;
    --cleanup) CLEANUP=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$INPUT_BIN" && -n "$INPUT_JSON" ]]; then
  # If input-bin is set explicitly, ignore JSON default only when default was untouched.
  if [[ "$INPUT_JSON" != "input.json" ]]; then
    echo "--input and --input-bin are mutually exclusive" >&2
    exit 1
  fi
fi

manifest_abs="$(python3 - "$MANIFEST" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
if [[ ! -f "$manifest_abs" ]]; then
  echo "Manifest not found: $manifest_abs" >&2
  exit 1
fi
manifest_dir="$(dirname "$manifest_abs")"

if [[ -z "$ACCOUNTS" ]]; then
  ACCOUNTS="$manifest_dir/frostbite-accounts.toml"
else
  ACCOUNTS="$(python3 - "$ACCOUNTS" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
fi

if [[ -z "$PROGRAM" ]]; then
  PROGRAM="$manifest_dir/guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest"
else
  PROGRAM="$(python3 - "$PROGRAM" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
fi

if [[ -n "$WEIGHTS" ]]; then
  WEIGHTS="$(python3 - "$WEIGHTS" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
fi

if [[ -n "$INPUT_BIN" ]]; then
  INPUT_BIN="$(python3 - "$INPUT_BIN" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
elif [[ -n "$INPUT_JSON" ]]; then
  INPUT_JSON="$(python3 - "$INPUT_JSON" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
fi

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

run_cauldron() {
  run "${CAULDRON[@]}" "$@"
}

manifest_has_weights="$(python3 - "$manifest_abs" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    m = tomllib.load(fh)
print("1" if isinstance(m.get("weights"), dict) else "0")
PY
)"

if [[ -z "$INSTRUCTIONS" || -z "$MAX_TX" ]]; then
  layout="$(python3 - "$manifest_abs" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    m = tomllib.load(fh)
weights = m.get("weights") if isinstance(m, dict) else None
layout = ""
if isinstance(weights, dict):
    v = weights.get("layout")
    if isinstance(v, str):
        layout = v
print(layout)
PY
)"
  if [[ "$layout" == *"cnn1d"* || "$layout" == *"tiny_cnn"* ]]; then
    [[ -z "$INSTRUCTIONS" ]] && INSTRUCTIONS=10000
    [[ -z "$MAX_TX" ]] && MAX_TX=120
  else
    [[ -z "$INSTRUCTIONS" ]] && INSTRUCTIONS=50000
    [[ -z "$MAX_TX" ]] && MAX_TX=10
  fi
fi

extra_network_args=()
[[ -n "$RPC_URL" ]] && extra_network_args+=(--rpc-url "$RPC_URL")
[[ -n "$PAYER" ]] && extra_network_args+=(--payer "$PAYER")
[[ -n "$PROGRAM_ID" ]] && extra_network_args+=(--program-id "$PROGRAM_ID")
output_network_args=()
[[ -n "$RPC_URL" ]] && output_network_args+=(--rpc-url "$RPC_URL")

weights_bin=""
if [[ -n "$WEIGHTS" ]]; then
  case "${WEIGHTS##*.}" in
    bin|BIN)
      weights_bin="$WEIGHTS"
      ;;
    *)
      run_cauldron convert --manifest "$manifest_abs" --input "$WEIGHTS" --pack
      weights_bin="$manifest_dir/weights.bin"
      ;;
  esac
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  run_cauldron build-guest --manifest "$manifest_abs"
fi

if [[ "$SKIP_ACCOUNTS" -eq 0 ]]; then
  run_cauldron accounts init --manifest "$manifest_abs" --out "$ACCOUNTS" --ram-count "$RAM_COUNT" "${extra_network_args[@]}"
  run_cauldron accounts create --accounts "$ACCOUNTS"
fi

if [[ "$SKIP_UPLOAD" -eq 0 && "$manifest_has_weights" == "1" ]]; then
  if [[ -z "$weights_bin" ]]; then
    weights_bin="$manifest_dir/weights.bin"
  fi
  if [[ ! -f "$weights_bin" ]]; then
    echo "Weights binary not found for upload: $weights_bin" >&2
    echo "Provide --weights or generate weights.bin first." >&2
    exit 1
  fi
  run_cauldron upload --file "$weights_bin" --accounts "$ACCOUNTS" "${extra_network_args[@]}"
fi

if [[ -n "$INPUT_BIN" ]]; then
  run_cauldron input-write --manifest "$manifest_abs" --accounts "$ACCOUNTS" --input-bin "$INPUT_BIN" "${extra_network_args[@]}"
else
  if [[ ! -f "$INPUT_JSON" ]]; then
    echo "Input JSON not found: $INPUT_JSON" >&2
    exit 1
  fi
  run_cauldron input-write --manifest "$manifest_abs" --accounts "$ACCOUNTS" --data "$INPUT_JSON" "${extra_network_args[@]}"
fi

if [[ "$SKIP_LOAD" -eq 0 ]]; then
  if [[ ! -f "$PROGRAM" ]]; then
    echo "Guest program not found: $PROGRAM" >&2
    echo "Run build first or pass --program." >&2
    exit 1
  fi
  run_cauldron program load --accounts "$ACCOUNTS" "$PROGRAM" "${extra_network_args[@]}"
fi

run_cauldron invoke --accounts "$ACCOUNTS" --fast --instructions "$INSTRUCTIONS" --max-tx "$MAX_TX" "${extra_network_args[@]}"

if [[ "$SKIP_OUTPUT" -eq 0 ]]; then
  run_cauldron output --manifest "$manifest_abs" --accounts "$ACCOUNTS" "${output_network_args[@]}"
fi

if [[ "$CLEANUP" -eq 1 ]]; then
  cleanup_script="$repo_root/scripts/cauldron-seeded-cleanup.sh"
  if [[ ! -x "$cleanup_script" ]]; then
    echo "Cleanup script not found/executable: $cleanup_script" >&2
    exit 1
  fi
  run "$cleanup_script" --accounts "$ACCOUNTS" "${extra_network_args[@]}"
fi

echo "Done."
