#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/cauldron-seeded-cleanup.sh [options]

Close seeded VM/segment accounts and reclaim rent.

Options:
  --accounts <path>        Accounts file (default: ./frostbite-accounts.toml)
  --rpc-url <url>          RPC URL override
  --payer <path>           Payer keypair override
  --program-id <pubkey>    Program id override
  --dry-run                Print commands without executing
  -h, --help               Show this help
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if command -v cauldron >/dev/null 2>&1; then
  CAULDRON=(cauldron)
else
  CAULDRON=(python3 -m cauldron.cli)
fi

ACCOUNTS="frostbite-accounts.toml"
RPC_URL=""
PAYER=""
PROGRAM_ID=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --accounts) ACCOUNTS="$2"; shift 2 ;;
    --rpc-url) RPC_URL="$2"; shift 2 ;;
    --payer) PAYER="$2"; shift 2 ;;
    --program-id) PROGRAM_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

ACCOUNTS="$(python3 - "$ACCOUNTS" <<'PY'
import os, sys
print(os.path.abspath(sys.argv[1]))
PY
)"
if [[ ! -f "$ACCOUNTS" ]]; then
  echo "Accounts file not found: $ACCOUNTS" >&2
  exit 1
fi

extra_network_args=()
[[ -n "$RPC_URL" ]] && extra_network_args+=(--rpc-url "$RPC_URL")
[[ -n "$PAYER" ]] && extra_network_args+=(--payer "$PAYER")
[[ -n "$PROGRAM_ID" ]] && extra_network_args+=(--program-id "$PROGRAM_ID")

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

run_cauldron() {
  run "${CAULDRON[@]}" "$@"
}

segments="$(python3 - "$ACCOUNTS" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
segments = data.get("segments")
if not isinstance(segments, list):
    sys.exit(0)
# Close RAM first (descending slot), then weights.
ram = []
weights = []
for seg in segments:
    if not isinstance(seg, dict):
        continue
    kind = seg.get("kind")
    slot = seg.get("slot")
    if not isinstance(kind, str) or not isinstance(slot, int):
        continue
    if kind == "ram":
        ram.append(slot)
    elif kind == "weights":
        weights.append(slot)
for s in sorted(set(ram), reverse=True):
    print(f"ram {s}")
for s in sorted(set(weights), reverse=True):
    print(f"weights {s}")
PY
)"

failures=0

if [[ -n "$segments" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    kind="${line%% *}"
    slot="${line##* }"
    if ! run_cauldron accounts close-segment --accounts "$ACCOUNTS" --kind "$kind" --slot "$slot" "${extra_network_args[@]}"; then
      echo "WARN: close-segment failed for kind=$kind slot=$slot" >&2
      failures=$((failures + 1))
    fi
  done <<< "$segments"
fi

if ! run_cauldron accounts close-vm --accounts "$ACCOUNTS" "${extra_network_args[@]}"; then
  echo "WARN: close-vm failed" >&2
  failures=$((failures + 1))
fi

if [[ "$failures" -ne 0 ]]; then
  echo "Cleanup finished with $failures warning(s)." >&2
  exit 1
fi

echo "Cleanup complete."
