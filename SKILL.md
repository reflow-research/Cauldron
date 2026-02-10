---
name: frostbite-cauldron
description: Build, train, convert, and deploy Frostbite/Cauldron on-chain AI models on Solana, including manifest authoring, guest builds, seeded deterministic account lifecycle, weight upload, and on-chain inference workflows.
---

# Cauldron (Frostbite ModelKit)

## Scope

Use this skill when asked about:

- Cauldron CLI flows (`init`, `convert`, `build-guest`, `upload`, `invoke`)
- Frostbite account lifecycle and deterministic account mapping
- On-chain inference testing on devnet
- Template-specific model setup (`linear`, `mlp*`, `cnn1d`, `tiny_cnn`, `tree`, `custom`)

## Canonical Workflow (Current)

1. Initialize:

```bash
cauldron init <dir> --template <template>
```

2. Prepare weights + manifest:

```bash
cauldron convert --manifest frostbite-model.toml --input <weights> --pack
```

3. Build guest:

```bash
cauldron build-guest --manifest frostbite-model.toml
```

4. Initialize seeded deterministic accounts:

```bash
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts create --accounts frostbite-accounts.toml
```

5. Upload weights:

```bash
cauldron upload --file weights.bin --accounts frostbite-accounts.toml
```

6. Load + run:

```bash
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest
# repeat the next three commands per inference
cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

Shortcut wrapper:

```bash
./scripts/cauldron-devnet-fastpath.sh \
  --manifest frostbite-model.toml \
  --weights weights.json \
  --input input.json
```

## TUI Workflow (Wizard + Manual)

Launch:

```bash
cauldron tui
```

Current behavior:

- Mode picker offers `Wizard` (guided) and `Manual` (panel-based).
- Manual mode panel order is `Models`, `Train`, `Weights`, `Accounts`, `Invoke`.
- For new projects entering Manual directly, run `Models -> Initialize Project` first.
- You can also run this from the command palette (`Ctrl+P`) via `Initialize Project`.

Manual first-run sequence:

1. `Models -> Initialize Project` (validates manifest + writes accounts config)
2. `Accounts -> Create Accounts`
3. `Weights` actions (convert/pack/chunk/upload as needed)
4. `Invoke` actions (`input-write -> invoke -> output`)

## Deterministic Account Model (Seeded v3)

- Recommended workflow is seeded deterministic account derivation (`create_with_seed`).
- `accounts init` uses this mode by default (or `vm.seed` in `frostbite-accounts.toml`).
- `accounts init` writes `vm.entry` for fresh restart execution defaults.
- Use `--legacy-accounts` only for manual non-seeded account mode.
- `vm.seed` + authority determines VM address.
- Segment address is derived from authority + `vm.seed` + kind + slot.
- Segment slot constraints:
  - `1` = weights
  - `2..15` = RAM
- `accounts init --ram-count` supports at most 14 RAM segments in seeded mode.

Authority notes:

- If authority differs from payer, set `vm.authority_keypair` explicitly.
- Keep `frostbite-accounts.toml` as source of truth for `seed`, authority, slots.

Lifecycle helpers:

```bash
cauldron accounts clear --accounts frostbite-accounts.toml --kind ram --slot 2 --offset 0 --length 0
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```

Shortcut cleanup:

```bash
./scripts/cauldron-seeded-cleanup.sh --accounts frostbite-accounts.toml
```

## Invoke Guidance (Important)

For heavier templates (`cnn1d`, `tiny_cnn`) use smaller slices:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 10000 --max-tx 120
```

For typical lighter templates (`linear`, `softmax`, `naive_bayes`, `mlp*`,
`two_tower`, `tree`, `custom`) this is usually sufficient:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
```

`cauldron invoke` auto-sets `--ram-count 0` when mapped `rw:` segments already
exist.
`cauldron invoke` defaults to seeded fresh-restart mode. Use `--mode resume`
only when you intentionally want persistent VM runtime state.
If output is read immediately after invoke on shared RPC, use signature-gated
reads: `cauldron invoke --sig-out <path>` then
`cauldron output --after-signature-file <path> --commitment finalized`.
`cauldron upload` rejects source-format files (`.json`, `.npz`, `.pt`, etc.) by
default; upload `weights.bin` or pass `--allow-raw-upload` explicitly.

## Template Input Reminders

- `cnn1d` (`time_series`): payload must be nested `window x features`.
- `tiny_cnn` (`vector`): payload shape should match `input_shape` (for default
  template: `28 x 28`).
- `custom`: provide raw blob bytes (`--input-bin`) or JSON payload bytes.

## Docs to Open

- `README.md`
- `CAULDRON.md`
- `docs/RUNNING_EXAMPLES.md`
- `docs/FROSTBITE_MODEL_SPEC.md`
- `docs/FROSTBITE_GUEST_CONTRACT.md`
- `docs/FROSTBITE_PDA_ACCOUNT_MODEL_V3.md`
- `examples/models/README.md`

## Safety and Testing Expectations

- Default to devnet unless user explicitly requests otherwise.
- Validate with real on-chain transactions for release readiness.
- Prefer deterministic seeded accounts for multi-user safety.
- Reclaim rent after tests with `close-segment` and `close-vm`.
