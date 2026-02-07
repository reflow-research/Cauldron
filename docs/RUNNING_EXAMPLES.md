# Running Examples (Devnet)

This is a minimal end-to-end flow for a linear model on devnet using the
current seeded deterministic account model.

## Prereqs
- `frostbite-run-onchain` on PATH or set `FROSTBITE_RUN_ONCHAIN`
- Payer keypair (default: `~/.config/solana/id.json`)
- Solana CLI pointed at devnet (or pass `--rpc-url`)

Note: keep `abi.entry >= 0x4000` so guest code does not overwrite VM
header/control block. Templates already default to `0x4000`.

## 1) Create a project

```bash
cauldron init demo-linear --template linear
cd demo-linear
```

Optional: swap in an example manifest (re-run `build-guest` after copying).

```bash
cp ../examples/models/linear-liquidity.frostbite-model.toml frostbite-model.toml
```

## 2) Create weights + build guest

```bash
python3 - <<'PY'
import json
w = [float(i % 8 - 4) for i in range(64)]
b = [0.25]
json.dump({"w": w, "b": b}, open("weights.json", "w"))
PY

cauldron convert --manifest frostbite-model.toml --input weights.json --pack
cauldron build-guest --manifest frostbite-model.toml
```

## 3) Create seeded VM/segment accounts

Initialize deterministic account metadata (single weights + single RAM segment):

```bash
cauldron accounts init --manifest frostbite-model.toml --ram-count 1 \
  --rpc-url https://api.devnet.solana.com \
  --payer ~/.config/solana/id.json
```

Create the VM and segments on-chain from `frostbite-accounts.toml`:

```bash
cauldron accounts create --accounts frostbite-accounts.toml
```

Inspect derived addresses:

```bash
cauldron accounts show --accounts frostbite-accounts.toml
```

## 4) Upload, stage input, invoke, read output

```bash
cauldron upload --file weights.bin --accounts frostbite-accounts.toml

python3 - <<'PY'
import json
json.dump(list(range(1, 65)), open("input.json", "w"))
PY

cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

For repeated inferences, keep the same VM/segments and only repeat
`input-write -> invoke -> output`. In seeded mode, fresh execution is the
default (`--mode fresh`) and does not require a VM clear between runs.

## Template invoke guidance

Use smaller instruction slices for heavier templates to avoid single-tx CU exhaustion:

```bash
# Recommended for cnn1d and tiny_cnn on devnet
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 10000 --max-tx 120
```

Typical lighter templates (`linear`, `softmax`, `naive_bayes`, `mlp*`, `two_tower`, `tree`, `custom`) work with:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
```

## Cleanup (reclaim rent)

```bash
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```

## Notes

- `cauldron upload` writes an RVCD v1 header into the weights segment.
  Ensure `weights.header_format = "rvcd-v1"` and `data_offset = 12` where used.
- `cauldron upload` blocks source-format files (`weights.json`, `.npz`, `.pt`,
  etc.) by default. Convert first, then upload `weights.bin`.
- `cauldron accounts init` defaults to seeded deterministic mode; pass
  `--legacy-accounts` only for manual legacy account handling.
- `cauldron invoke` auto-sets `--ram-count 0` when mapped `rw:` segments already
  exist in the accounts mapping.
- `cauldron invoke` defaults to fresh seeded restart (`--mode fresh`).
  Use `--mode resume` only when you intentionally need persistent runtime state.
- If no writable mapped segment exists, runner fallback RAM defaults to `256 KiB`
  per temporary segment (override with `--ram-bytes`).
- If output appears stale immediately after invoke on shared RPC, run invoke with
  `--verbose`, confirm the execute signature at `finalized`, then read output.

## Troubleshooting

- `ProgramFailedToComplete` on first invoke: reduce per-tx slice (`--instructions 10000`) and retry.
- `time_series window length mismatch` for `cnn1d`: provide a nested `window x features` JSON shape.
- `ERR_SCHEMA` on tree templates with placeholder weights: regenerate with current `cauldron init` (tree placeholders now emit valid leaf nodes).
- Runner not found: set `FROSTBITE_RUN_ONCHAIN` to the full binary path.
