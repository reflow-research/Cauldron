# Cauldron SDK Guide

Cauldron is the Frostbite model SDK + CLI for on-chain inference on Solana.
This guide is the practical path for humans and agents shipping real devnet
runs with deterministic seeded accounts.

Core capabilities:

- model manifest validation and patching
- guest build for RISC-V (`rv64imac`)
- weights conversion/packing/upload
- deterministic seeded account lifecycle
- on-chain inference on Solana

## Recommended Default: Seeded Deterministic Accounts

For multi-user and production-style flows, use the seeded deterministic account
path (v3 opcodes). `accounts init` now defaults to this mode.

- VM and segment addresses are derived from authority + `vm.seed` + kind/slot.
- Slot `1` is weights, slots `2..15` are RAM.
- Multi-user isolation is achieved by authority namespace + seed.

Use:

```bash
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts create --accounts frostbite-accounts.toml
```

Use `--legacy-accounts` only when you intentionally need manual non-seeded
account management.

## Standard End-to-End Flow

```bash
cauldron init my-model --template linear
cd my-model

cauldron convert --manifest frostbite-model.toml --input weights.json --pack
cauldron build-guest --manifest frostbite-model.toml

cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts create --accounts frostbite-accounts.toml

cauldron upload --file weights.bin --accounts frostbite-accounts.toml
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest

# repeat this block for each inference
cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

Wrapper script for this flow:

```bash
./scripts/cauldron-devnet-fastpath.sh \
  --manifest frostbite-model.toml \
  --weights weights.json \
  --input input.json
```

## Invoke Presets

Heavier templates (`cnn1d`, `tiny_cnn`) should use smaller slices:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 10000 --max-tx 120
```

Lighter templates (`linear`, `softmax`, `naive_bayes`, `mlp*`, `two_tower`,
`tree`, `custom`) generally work with:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
```

## Account Lifecycle Commands

```bash
cauldron accounts show --accounts frostbite-accounts.toml
cauldron accounts clear --accounts frostbite-accounts.toml --kind ram --slot 2 --offset 0 --length 0
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```

Or use:

```bash
./scripts/cauldron-seeded-cleanup.sh --accounts frostbite-accounts.toml
```

## Important Notes

- `cauldron invoke` auto-sets `--ram-count 0` when mapped writable segments are already present.
- `cauldron invoke` defaults to seeded fresh-restart mode (`--mode fresh`).
  Use `--mode resume` only when persistent runtime state is intentional.
- Runner fallback temporary RAM defaults to `262144` bytes (`256 KiB`) per segment.
- `cauldron upload` writes an RVCD v1 header into weights. Keep manifest
  `weights.header_format = "rvcd-v1"` and `data_offset = 12` where applicable.
- `cauldron upload` rejects source-format files (`.json`, `.npz`, `.pt`, etc.)
  unless `--allow-raw-upload` is set.
- For JS/TOML workflows, quote large seeds:
  - `vm.seed = "1234567890123456789"`
- For deterministic read-after-write on shared RPC endpoints:
  - invoke with `--verbose`, confirm the execute signature as `finalized`, then read output.

## Template Input Shape Reminders

- `cnn1d` (`time_series`): nested array of shape `window x features`.
- `tiny_cnn` (`vector`): nested array matching `input_shape` (default `28 x 28`).
- `custom`: use `--input-bin` or JSON payload bytes (`payload_hex` / `payload_base64`).

## Validation Snapshot

As of 2026-02-07, all shipped templates passed seeded-account devnet E2E runs:

- `linear`, `softmax`, `naive_bayes`, `two_tower`
- `mlp`, `mlp2`, `mlp3`
- `cnn1d`, `tiny_cnn`, `tree`, `custom`

Detailed semantic output checks are recorded in
`docs/validation/devnet-semantic-2026-02-07.csv`.

## Troubleshooting

- `ProgramFailedToComplete` on first invoke:
  - reduce slice size (`--instructions 10000`) and increase `--max-tx`.
- `time_series window length mismatch`:
  - provide `cnn1d` input as nested `window x features`.
- `ERR_SCHEMA` on tree with placeholder weights:
  - regenerate with current `cauldron init` (tree placeholders now use leaf sentinels).
- Runner discovery issues:
  - set `FROSTBITE_RUN_ONCHAIN` explicitly.

## Related Docs

- `README.md`
- `docs/RUNNING_EXAMPLES.md`
- `docs/FROSTBITE_MODEL_SPEC.md`
- `docs/FROSTBITE_GUEST_CONTRACT.md`
- `docs/FROSTBITE_PDA_ACCOUNT_MODEL_V3.md`
- `examples/models/README.md`
