# Cauldron (Frostbite ModelKit)

Cauldron is the Frostbite model SDK + CLI for on-chain inference on Solana.
It covers manifest authoring, guest template patching, RISC-V guest builds,
weights conversion/packing, deterministic account lifecycle, upload, and invoke.

Inference executes on-chain in the same transaction context as your other
program logic.

This repo and the included docs are designed to work well with agentic tooling.

Vibe-friendly tooling for Frostbite model manifests, guest templates, and
weights packaging.

Both `cauldron` and `frostbite-modelkit` point to the same CLI entrypoint.

## Quick start (dev)

```bash
cauldron init demo-linear --template linear
cd demo-linear
cauldron validate frostbite-model.toml
```

or:

```
python -m cauldron.cli validate path/to/frostbite-model.toml 
```
*Note* - see examples folder to get started with vendored model templates. 

## Validation status

As of 2026-02-07, all shipped templates passed end-to-end devnet execution in a
seeded deterministic-account sweep (`11/11`):

- `linear`, `softmax`, `naive_bayes`, `two_tower`
- `mlp`, `mlp2`, `mlp3`
- `cnn1d`, `tiny_cnn`, `tree`, `custom`

## CLI

- `cauldron init <dir> --template linear|softmax|naive_bayes|two_tower|mlp|mlp2|mlp3|cnn1d|tiny_cnn|tree|custom`
- `cauldron validate <manifest>`
- `cauldron show <manifest>`
- `cauldron build-guest --manifest <manifest>`
- `cauldron convert --manifest <manifest> --input <weights.(json|npz|npy|pt|pth|safetensors)>`
- `cauldron pack <manifest> [--update-size] [--dry-run] [--create-missing]`
- `cauldron chunk --manifest <manifest> [--chunk-size N]`
- `cauldron upload --file <chunk.bin> [--cluster devnet|mainnet|localnet|surfpool]`
- `cauldron deploy --manifest <manifest> --input <weights> [--upload]`
- `cauldron train --manifest <manifest> --data <dataset.csv|npz>`
- `cauldron accounts init --manifest <manifest> --ram-count 1`
- `cauldron accounts show --accounts frostbite-accounts.toml`
- `cauldron accounts create --accounts frostbite-accounts.toml`
- `cauldron accounts clear --accounts frostbite-accounts.toml --kind ram --slot 2 --offset 0 --length 0`
- `cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2`
- `cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1`
- `cauldron accounts close-vm --accounts frostbite-accounts.toml`
- `cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest` (load-only)
- `cauldron invoke --accounts frostbite-accounts.toml`
- `cauldron schema-hash --manifest <manifest> [--update-manifest]`
- `cauldron input --manifest <manifest> --data input.json [--header]`
- `cauldron input-write --manifest <manifest> --accounts frostbite-accounts.toml --data input.json`
- `cauldron output --manifest <manifest> --accounts frostbite-accounts.toml`

Note: `accounts create`, `invoke`, and `program load` require the
`frostbite-run-onchain` helper. Set `FROSTBITE_RUN_ONCHAIN` to its path, or
place the binary in `cauldron/bin/<platform>/` or `cauldron/toolchain/bin/<platform>/`
(auto-discovered). Otherwise it must be available on your PATH.

`cauldron invoke` disables temporary RAM account creation when your mapped
accounts already include writable segments (`rw:` lines), unless you override
with `--ram-count`.

`cauldron accounts init` now defaults to seeded deterministic accounts.
Use `--legacy-accounts` only when you intentionally want manual legacy account
management.

`frostbite-run-onchain` fallback RAM accounts default to `262144` bytes
(`256 KiB`) per segment; override with `cauldron invoke --ram-bytes` when needed.

This repo ships a prebuilt `frostbite-run-onchain` per platform
(`darwin-arm64`, `darwin-x64`, `linux-x64`, `linux-arm64`, `windows-x64`). If it doesn’t run
on your system, replace it and/or set `FROSTBITE_RUN_ONCHAIN`.

**Note**

If the vendored `frostbite-run-onchain` binary is older than your deployed
program behavior, replace it with a freshly built runner and/or set
`FROSTBITE_RUN_ONCHAIN` explicitly.

Install-time selectors for packaging:
- `scripts/select-runner.py` (pip / Python)
- `scripts/select-runner.js` (npm / Node)

Release/staging helper (run on each platform):
```
./scripts/build-runner-binaries.sh
```

Runner build profile note: use `--no-default-features --features cli`
for host binaries (`frostbite-run` / `frostbite-run-onchain`).

Postinstall helpers:
- pip: `cauldron-postinstall` (or `python -m cauldron.postinstall`)
- npm: `postinstall` runs `node scripts/select-runner.js --copy`

Packaging note: `MANIFEST.in` includes runner binaries, docs, and examples for
sdist builds.

The Frostbite program itself is pre-deployed (devnet v0). Cauldron defaults to
the devnet program ID; override with `FROSTBITE_PROGRAM_ID` or in the accounts
file if needed.

By default `init` copies the full guest template. Use `--stub` to generate a
minimal placeholder instead.

If Cauldron is installed without bundled templates, `init` will fall back to a
stub and emit a warning.

`init` will also create `weights.bin` placeholder files from the
manifest unless `--no-weights` is provided. Tree templates now emit valid
leaf-node placeholders (not all-zero blobs).

## Convert input format

Linear JSON example:
```
{
  "w": [0.1, -0.2, ...],
  "b": 0.03
}
```

MLP JSON example:
```
{
  "w1": [[...], [...]],
  "b1": [...],
  "w2": [[...]],
  "b2": [...]
}
```

MLP2/MLP3 JSON example:
```
{
  "w1": [[...]],
  "b1": [...],
  "w2": [[...]],
  "b2": [...],
  "w3": [[...]],
  "b3": [...],
  "w4": [[...]],
  "b4": [...]
}
```

CNN JSON example:
```
{
  "w1": [[[...]]],
  "b1": [...],
  "w2": [[...]],
  "b2": [...]
}
```
For `cnn1d`, `w1` is shaped `[out_channels][in_channels][kernel]`.
For `tiny_cnn`, `w1` is shaped `[out_channels][kernel][kernel]` (single-channel input).

`convert` infers dimensions from the manifest:
- `vector`: product of `input_shape` / `output_shape`
- `time_series`: `window * features`
- `graph`: `node_feature_dim` (default)

You can override with `--input-dim`, `--output-dim`, and `--hidden-dim` (MLP).
For MLP2/MLP3, use `--hidden-dim1/2(/3)` if you need to override manifest values.
It updates `weights.scales` unless `--no-update-manifest` is passed.

For PyTorch or safetensors, use `--keymap` to map your state dict keys to
`w`, `b`, `w1`, `b1`, `w2`, `b2`.

## Training harness

The training harness is a starter that trains a small model, calibrates
weights, and exports `weights.json` (and optionally `weights.bin`).

Example (MLP):
```
cauldron train --manifest frostbite-model.toml --data data.csv \
  --template mlp --epochs 50 --calibrate-percentile 99.5
```

For multi-class classification, set `schema.output_shape` to the number of
classes so the training harness matches the manifest dimensions.

Supported datasets:
- `.csv` (features + label column)
- `.npz` (`x` + `y`, or `x_a/x_b` for two_tower)

Optional deps for training:
```
pip install "frostbite-modelkit[train]"
```

For two-tower models, use `w1/b1` for tower A and `w2/b2` for tower B, and set
`build.tower_input_a`, `build.tower_input_b`, and `build.embed_dim` in the manifest.

For tree models, pass JSON with either `nodes` (single tree) or `trees`:
```
{
  "nodes": [
    {"feature": 0, "threshold": 0.1, "left": 1, "right": 2, "value": 0.0},
    {"feature": -1, "threshold": 0.0, "left": -1, "right": -1, "value": 0.2},
    {"feature": -1, "threshold": 0.0, "left": -1, "right": -1, "value": -0.1}
  ]
}
```
Each node is packed as five `i32` values (feature, threshold_q16, left, right, value_q16).
Tree manifests use `quantization = "custom"` and `dtype = "i32"`.
If `build.tree_stride` is larger than `tree_node_count * 20`, Cauldron pads each tree to the stride.

Note: `.pt/.pth` requires `torch` and `.safetensors` requires `safetensors`.

## Upload

`upload` wraps the bundled Rust tool:
```
cd cauldron/rust_tools
cargo run --bin upload_model -- <chunk.bin>
```

Cauldron can set `FROSTBITE_RPC_URL` and `FROSTBITE_PAYER_KEYPAIR` for the
upload tool. The Frostbite program ID is preconfigured for devnet.
If no overrides are provided, it uses the Solana CLI config values.

For single-account weights, you can upload the full `weights.bin` directly.
If model weights exceed single-account practical limits, use chunked upload and
segment planning per your deployment constraints.

Note: `cauldron upload` writes an RVCD v1 header into the weights account.
Set `weights.header_format = "rvcd-v1"` (and `data_offset = 12` if specified)
so guest code reads the correct weights offsets.
`cauldron upload` rejects source-format files (`.json`, `.npz`, `.pt`, etc.) by
default; upload the converted binary payload (`weights.bin`) instead.
Use `--allow-raw-upload` only for explicit advanced/debug cases.
If you do not specify RAM accounts, `invoke` will create a temporary RAM account
for the run. Use `accounts init --ram-file` for persistent RAM mappings.

## SDK examples

See `sdk/` for minimal JS/TS, Python, and Rust clients that invoke
Frostbite and read output bytes from the VM scratch account.
The optional gatekeeper program lives in `gatekeeper/` with a JS
example in `sdk/js/run_gatekeeper.js`. See
`gatekeeper/README.md` for build/deploy steps.
For deterministic seeded accounts in JS, keep large `vm.seed` values quoted
in TOML (`vm.seed = "1234567890123456789"`) to avoid numeric precision loss.

## Specs

- `docs/FROSTBITE_MODEL_SPEC.md`
- `docs/FROSTBITE_GUEST_CONTRACT.md`
- `docs/FROSTBITE_PDA_ACCOUNT_MODEL_V1.md`
- `examples/models/`

When installed via pip, the same files are bundled under
`cauldron/docs/` and `cauldron/examples/` inside site-packages.

## Input payloads

For vector/time_series, `input.json` can be a list or nested list.
For graph schemas, use an object:
```
{
  "nodes": [[...], [...]],
  "edges": [[0,1], [1,2]],
  "edge_features": [[...], [...]]
}
```

For custom schemas, pass `--input-bin` or provide `payload_hex`/
`payload_base64` in JSON.

## Fast path (preload + invoke)

Low-latency flow: preload guest + inputs, then invoke without upload delays.

```bash
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts create --accounts frostbite-accounts.toml
cauldron upload --file weights.bin --accounts frostbite-accounts.toml
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest
cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 50000 --max-tx 10
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

To stage input + control block directly into a VM account:
```bash
cauldron input-write --manifest frostbite-model.toml \
  --accounts frostbite-accounts.toml --data input.json
```

To preload the guest program into an existing VM and skip execution:
```bash
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest
```

For low-latency invocation (assumes program + input already staged):
```bash
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 50000 --max-tx 10
```

For heavier templates (`cnn1d`, `tiny_cnn`), use smaller slices:

```bash
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 10000 --max-tx 120
```

Recommended cleanup after tests:

```bash
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```
