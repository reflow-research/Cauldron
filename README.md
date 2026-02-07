# Cauldron (Frostbite ModelKit)

Cauldron allows you to design, train, upload, and invoke AI models on the Solana blockchain.

Cauldron interfaces with the frostbite RISC-V computer to invoke small AI models at execution time 
inside of a Solana transaction. Models invoked with cauldron have 0 latency for acting on data that is exposed to programs on Solana. This collapses the gap between off chain calculation and current Solana state. 

Cauldron was designed to be used alongside agentic coding tools. Point your agents at `SKILL.md` in the repo root and they will be able to guide you through designing, training, uploading, and invoking your own model. Frostbite is currently live on devnet, so point your Solana CLI to devnet to use Cauldron on the devnet cluster.
Use https://faucet.solana.com/ and connect your github to receive 10 devnet sol per 8 hours.  

One of the key benefits of actual on-chain AI is that inference happens at execution time with any data that is exposed to a Solana program. You can train models
that route dynamically, abort txns if toxic flow is detected, traverse and trim liquidity pool graphs, analyze pool depth and volume inflows, rebalance yield
portfolios, and detect if a token is likely a rug or not; to name a few examples. There is really no limit to what you can do provided you respect Solana constraints.

As far as we know, we are the first to do legitimate on-chain AI inference. We are keen to explore where this can go. A new environment of verifiable, trustless,
and financially meaningful AI is now upon us. PRs and contributions are welcome. We will be open sourcing the frostbite program in the future.


## Why on-chain inference

You can use inference at execution time for tasks like:
- Guarding transactions when toxic flow is detected.
- Routing based on current pool depth and liquidity conditions.
- Real-time risk checks that must match the exact state used by the
  transaction.

Both `cauldron` and `frostbite-modelkit` map to the same CLI entrypoint.

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

Detailed semantic output checks are recorded in
`docs/validation/devnet-semantic-2026-02-07.csv`.

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
- `cauldron invoke --accounts frostbite-accounts.toml --mode fresh`
- `cauldron invoke --accounts frostbite-accounts.toml --mode resume`
- `cauldron schema-hash --manifest <manifest> [--update-manifest]`
- `cauldron input --manifest <manifest> --data input.json [--header]`
- `cauldron input-write --manifest <manifest> --accounts frostbite-accounts.toml --data input.json`
- `cauldron output --manifest <manifest> --accounts frostbite-accounts.toml`

Note: `accounts create`, `invoke`, and `program load` require the
`frostbite-run-onchain` helper. Cauldron auto-discovers vendored binaries from
`cauldron/bin/<platform>/` and `cauldron/toolchain/bin/<platform>/` first.
Set `FROSTBITE_RUN_ONCHAIN` to override this selection. If no vendored or
override binary is available, the helper must be on your PATH.

`cauldron invoke` automatically handles temporary RAM account creation.
If you manage memory accounts manually (mapped `rw:` segments), temp RAM is
suppressed by default; pass `--ram-count` to explicitly request it.

`cauldron invoke` now defaults to **fresh seeded restart** semantics for
seeded-v3 accounts (runtime reset + entry PC restart each run).
Use `--mode resume` only when you intentionally want persistent VM execution
state across invocations. Fresh mode does not require a VM clear transaction
between inferences.

`cauldron accounts init` now defaults to seeded deterministic accounts (v3 memory model).
Use `--legacy-accounts` only when you intentionally want manual non-seeded
account management.
Seeded account files now include `vm.entry` (defaults to `abi.entry`, fallback
`0x4000`) so fresh invocations do not require per-run program reload.

`frostbite-run-onchain` fallback RAM accounts default to `262144` bytes
(`256 KiB`) per segment; override with `cauldron invoke --ram-bytes` when needed.

This repo vendors a prebuilt `frostbite-run-onchain` per platform
(`darwin-arm64`, `darwin-x64`, `linux-x64`, `linux-arm64`, `windows-x64`). If it doesn’t run
on your system, replace it and/or set `FROSTBITE_RUN_ONCHAIN`.

**Note**

Install-time selectors for packaging:
- `scripts/select-runner.py` (pip / Python)
- `scripts/select-runner.js` (npm / Node)

Release/staging helper (run on each platform):
```
./scripts/build-runner-binaries.sh
```

GitHub cross-platform build + optional release:
- Workflow: `.github/workflows/build-runners-and-release.yml`
- Builds: `linux-x64`, `linux-arm64`, `darwin-x64`, `windows-x64`
- Optional release creation: set `release_tag` in workflow inputs

**Note**

Runner build profile note: use `--no-default-features --features cli`
for host binaries (`frostbite-run` / `frostbite-run-onchain`).
Use this profile for host binaries to match the documented runner build path.

Postinstall helpers:
- pip: `cauldron-postinstall` (or `python -m cauldron.postinstall`)
- npm: `postinstall` runs `node scripts/select-runner.js --copy`

Packaging note: `MANIFEST.in` includes runner binaries, docs, and examples for
sdist builds.

The Frostbite program itself is pre-deployed (devnet). Cauldron defaults to
the devnet program ID; override only if you intentionally target another deployment.

By default `init` copies the full guest template. Use `--stub` to generate a
minimal placeholder instead.

If Cauldron is installed without bundled templates, `init` will fall back to a
stub and emit a warning. However, this is unlikely to happen. 

`init` will also create `weights.bin` placeholder files from the
manifest unless `--no-weights` is provided. Tree templates emit valid
leaf-node placeholders.

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

**Note** 

You must use `cauldron convert` on your weight files to convert them to a `.bin` file before uploading. Frostbite expects raw bytes on chain.

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
weights, and exports `weights.bin` (and optionally, `weights.json`).

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
upload tool. You do not need to pass either unless you want to override your
default Solana CLI RPC URL or keypair.

The Frostbite program ID is preconfigured for devnet.
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
for the run.

*Use `accounts init --ram-count` for deterministic persistent RAM segments, or
`accounts init --ram-file` to import an existing mapped RAM file.*

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
- `docs/FROSTBITE_PDA_ACCOUNT_MODEL_V3.md`
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

Low-latency flow: preload guest once, then repeat input-write + invoke without
upload or reload delays.
You will want to use a low-latency flow for HFT/MM strategies and other atomic actions.
We recommend building a shell script to suit your needs once you have your model designed
and uploaded. 

```bash
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts create --accounts frostbite-accounts.toml
cauldron upload --file weights.bin --accounts frostbite-accounts.toml
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest

# repeat this block for each inference
cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
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
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 50000 --max-tx 10
```

For heavier templates (`cnn1d`, `tiny_cnn`), use smaller slices:

```bash
cauldron invoke --accounts frostbite-accounts.toml --mode fresh --fast --instructions 10000 --max-tx 120
```

If you are reading immediately after invoke on shared RPC endpoints, use
`--verbose` on invoke and confirm the execution signature before reading:

```bash
solana confirm --url https://api.devnet.solana.com --commitment finalized <EXECUTE_SIGNATURE>
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

Scripted wrapper for this full flow:

```bash
./scripts/cauldron-devnet-fastpath.sh \
  --manifest frostbite-model.toml \
  --weights weights.json \
  --input input.json
```

Recommended cleanup after tests:

```bash
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```

Scripted cleanup (closes RAM/weights segments, then VM):

```bash
./scripts/cauldron-seeded-cleanup.sh --accounts frostbite-accounts.toml
```
