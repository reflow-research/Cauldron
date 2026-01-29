# Cauldron SDK (Vibe-First)

Cauldron is the Frostbite model SDK + CLI designed for fast, friendly model
creation. It handles manifest validation, guest template patching, RISC-V
builds, weight conversion, chunking, and uploads.

Both `cauldron` and `frostbite-modelkit` point to the same CLI entrypoint.

## Quickstart

```
cauldron init my-model --template linear
cd my-model
cauldron convert --manifest frostbite-model.toml --input weights.json --pack
cauldron build-guest --manifest frostbite-model.toml
cauldron chunk --manifest frostbite-model.toml
cauldron upload --all "weights_chunk*.bin" --cluster devnet
```

Note: `cauldron upload` writes an RVCD v1 header into weights accounts. Use
`weights.header_format = "rvcd-v1"` (and `data_offset = 12` if specified) so
guest code reads weights at the correct offset.

## Running examples (devnet)

See `docs/RUNNING_EXAMPLES.md` for a full devnet walkthrough (weights, guest
build, on-chain invoke). Keep `abi.entry >= 0x4000` so guest code does not
overwrite the VM header/control block.

## Common flows

### Linear / Softmax / Naive Bayes / MLP
1) Train a model however you like.
2) Export weights to JSON/NPZ/NPY/PT/Safetensors with keys `w`,`b` or `w1`,`b1`,`w2`,`b2`.
3) Run `cauldron convert` + `cauldron pack`.
4) `cauldron build-guest` to compile the guest ELF.
5) `cauldron chunk` + `cauldron upload` to push weights on-chain.

### MLP-2 / MLP-3
1) Use `--template mlp2` or `--template mlp3` with `build.hidden_dim1/2(/3)`.
2) Export weights to JSON/NPZ/NPY/PT/Safetensors with keys `w1`,`b1`,`w2`,`b2`,`w3`,`b3` (and `w4`,`b4` for mlp3).
3) Run `cauldron convert`, `cauldron build-guest`, `cauldron chunk`, `cauldron upload`.

### CNN1D / Tiny-CNN
1) Use `--template cnn1d` (time_series schema) or `--template tiny_cnn` (vector schema).
2) Set `build.kernel_size`, `build.out_channels`, and `build.stride` (plus `build.input_height/width` for tiny_cnn).
3) Export weights with keys `w1`,`b1`,`w2`,`b2` and run `cauldron convert`.

### Two-tower similarity
1) Use `--template two_tower` and set `build.tower_input_a`, `build.tower_input_b`, `build.embed_dim`.
2) Provide weights as `w1`, `b1`, `w2`, `b2` (see manifest for layout).
3) `cauldron convert`, `cauldron build-guest`, `cauldron chunk`, `cauldron upload`.

### Tree / GBDT
1) Use `--template tree` with `build.tree_count` and `build.tree_node_count`.
2) Provide weights as JSON with `nodes` or `trees` (see ModelKit README for layout).
3) `cauldron convert`, `cauldron build-guest`, `cauldron chunk`, `cauldron upload`.

## Training harness

Cauldron includes a starter training CLI that can fit small models and export
quantized weights:

```
cauldron train --manifest frostbite-model.toml --data data.csv \
  --template mlp --epochs 50 --calibrate-percentile 99.5
```

It writes `weights.json` and (unless `--no-convert`) generates `weights.bin` +
updates `weights.scales` in the manifest.

For multi-class classification, set `schema.output_shape` to the number of
classes so the training harness matches the manifest dimensions.

### Custom schema
1) Define `schema.custom` in the manifest and describe layout in `layout.md`.
2) Use `cauldron schema-hash --update-manifest` to pin the schema hash.
3) Build your own `weights.bin` (custom tooling).
4) `cauldron build-guest` for the guest template.

## Key options

- `cauldron build-guest --schema-hash auto|manifest|none`
- `cauldron convert --keymap w=linear.weight --keymap b=linear.bias`
- `cauldron upload --cluster devnet --payer ~/.config/solana/id.json`
- `cauldron deploy --upload` for the full pipeline
- `cauldron input --manifest frostbite-model.toml --data input.json` to pack input payloads
- `cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json`
- `cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml`
- `cauldron accounts init --manifest frostbite-model.toml --ram-count 1`
- `cauldron accounts show --accounts frostbite-accounts.toml`
- `cauldron accounts create --accounts frostbite-accounts.toml`
- `cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest` (load-only)
- `cauldron invoke --accounts frostbite-accounts.toml --instructions 50000`

## Optional deps

- `numpy` for `.npy` and `.npz`
- `torch` for `.pt/.pth`
- `safetensors` for `.safetensors`

## SDK examples

Minimal JS/TS, Python, and Rust examples live in `sdk/`.
The optional on-chain gatekeeper example lives in `gatekeeper/`.
See `gatekeeper/README.md` for build/deploy steps.

## Specs

- `docs/FROSTBITE_MODEL_SPEC.md`
- `docs/FROSTBITE_GUEST_CONTRACT.md`
- `examples/models/`

When installed via pip, the same files are bundled under
`cauldron/docs/` and `cauldron/examples/` inside site-packages.

## Input payload formats

Vector/time_series payloads can be lists or nested lists.

Graph payload example:
```
{
  "nodes": [[...], [...]],
  "edges": [[0,1], [1,2]],
  "edge_features": [[...], [...]]
}
```

Custom payloads can be passed via `--input-bin` or JSON with `payload_hex` or
`payload_base64`.

## Cluster overrides

Cauldron can set environment variables consumed by the bundled Rust helpers:

- `FROSTBITE_RPC_URL`
- `FROSTBITE_PAYER_KEYPAIR`

The Frostbite program ID is preconfigured for devnet.
The program itself is already deployed for devnet v0, so users do not need to
deploy it.

If you select `--cluster surfpool`, provide `--rpc-url` or set
`SURFPOOL_RPC_URL`.

## Devnet shared VM/RAM accounts (updated 2026-01-28)

The Frostbite devnet program has a set of pre-funded VM and RAM accounts that
can be reused to avoid large devnet SOL spends.

Ownership / usage notes:
- These accounts are program-owned. No private keys are required to use them.
- There is no access control: any user can overwrite VM state or RAM contents.
  Treat them as shared scratch. Do not store secrets or rely on persistence.
- Use your own weights accounts (PDA/keypair) and your own guest program PDAs.
- Legacy oversized VM accounts (~614KB) remain valid because Frostbite only
  enforces a minimum size. The canonical VM size is 262,689 bytes.
- If you need isolation or stable RAM, create your own VM/RAM accounts.

VM accounts (legacy oversized, still valid):
- 8twJztqwdoPyi6v6KA2YcR2auH7pPegskWXsyESZzQrP
- 52Q2ZUfTDP46kfJAbf5jKTMTuRqHgRgU8YS6SBYRPktp
- 5mQw87fdxfEjv3pg89aQW9NE3gsb2EqPA4QvBkJMS4PH
- 8D6yTQvkA4YobPFF95M6Uw848bwiT6qRuPXDSZgci9Fx
- AjinBnLJPa77yuQGxGpYYbNuuiNRqnvVS9kLv5dvuVkS
- CdHFGc21n7iVMaBHGCeRwLnb9SR2ah9C8S3qJT9dMQk5
- G3LS9imZmbNpCBmCSd8GhSpvQEZDDbc8jDarb9P2XLZp
- H2NJGZcdrTvZE4TaGmdpSxpbGnk8UpNZwR2i1uVbgkw3

VM accounts (canonical size, 262,689 bytes):
- EZcnmSFyxdm7qNHdt1xjVcgNh3GEs5cBErJRDWdcVvfq
- 9b9ogpfyfpNejyA9Jzq8YSW8v2XepiPrSWbnZ9qS3LrY
- FgBoEPRtV31VerkVtAqYYMn53n9uxx1o9Rimjz8F5CdV
- 2gktRqhgSQK26eD6bchEtTQ8YtNNKnyPATzVLzTrqB1S
- NZJSPYDTyPsZ2Reqtz6DFP7TGjunLyKCZWATDfVDqPr

RAM accounts (4 MB each, writable):
- rw:CZq7wPvvQYaFiVXn6MTS1ZAAJathYH8N8a9UJTzkgnSP
- rw:ZHLUK4zdMKm3LgJqVo9fcb93g3dDUGzgrmQToeuK2cE
- rw:CaZNX6z3K8PBpcbduoiHsaVn6tw4itgAQKbNkygXSJJd
- rw:EnoTk59RWR5U38j6dumESYJwgtRNMohdRwRZC4vUNJxh

Example usage:
```
# ram_accounts_devnet.txt
rw:CZq7wPvvQYaFiVXn6MTS1ZAAJathYH8N8a9UJTzkgnSP
rw:ZHLUK4zdMKm3LgJqVo9fcb93g3dDUGzgrmQToeuK2cE
rw:CaZNX6z3K8PBpcbduoiHsaVn6tw4itgAQKbNkygXSJJd
rw:EnoTk59RWR5U38j6dumESYJwgtRNMohdRwRZC4vUNJxh

cauldron accounts init --manifest frostbite-model.toml \
  --vm EZcnmSFyxdm7qNHdt1xjVcgNh3GEs5cBErJRDWdcVvfq \
  --ram-file ram_accounts_devnet.txt
```

## Accounts mapping

Cauldron can manage a unified accounts file that maps VM + segment accounts in
order. Segment ordering matters: the first mapped account is segment 1, the
next is segment 2, etc.

Note: `accounts create`, `invoke`, and `program load` use the
`frostbite-run-onchain` helper. Set `FROSTBITE_RUN_ONCHAIN` to its path, or
place the binary in `cauldron/bin/<platform>/` or `cauldron/toolchain/bin/<platform>/`
(auto-discovered). Otherwise it must be available on your PATH.

This repo ships a prebuilt `frostbite-run-onchain` per platform
(`darwin-arm64`, `darwin-x64`, `linux-x64`, `linux-arm64`, `windows-x64`). If it doesn’t run
on your system, replace it and/or set `FROSTBITE_RUN_ONCHAIN`.

Install-time selectors for packaging:
- `scripts/select-runner.py` (pip / Python)
- `scripts/select-runner.js` (npm / Node)

Release/staging helper (run on each platform):
```
./scripts/build-runner-binaries.sh
```

Postinstall helpers:
- pip: `cauldron-postinstall` (or `python -m cauldron.postinstall`)
- npm: `postinstall` runs `node scripts/select-runner.js --copy`

Packaging note: `MANIFEST.in` includes runner binaries, docs, and examples for
sdist builds.

```
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
cauldron accounts show --accounts frostbite-accounts.toml
```

For uploads, provide a weights **keypair** in the accounts file and pass
`--accounts` to `cauldron upload` or `cauldron deploy`.

Single-account weights can be uploaded by passing `weights.bin` directly to
`cauldron upload --file weights.bin --accounts frostbite-accounts.toml`.

## Fast path (preload + invoke)

Low-latency flow: preload the guest program and inputs, then invoke without
upload delays.
After `accounts init`, fill in the VM/weights/RAM keypairs in
`frostbite-accounts.toml` (or pass `--vm-keypair`/`--weights-keypair`/
`--ram-keypair`) before creating accounts or uploading.
You also need a VM account initialized by the Frostbite program (for example,
run the following once to create the VM, then copy the pubkey into the accounts
file):

```
frostbite-run-onchain guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest \
  --vm-save frostbite_vm_accounts.txt
```

```
# 1) Create accounts file + VM account
cauldron accounts init --manifest frostbite-model.toml --ram-count 1
# (fill keypairs + VM pubkey in frostbite-accounts.toml)

# 2) Upload weights (creates weights account)
cauldron upload --file weights.bin --accounts frostbite-accounts.toml

# 3) Create RAM accounts (optional if you already have them)
cauldron accounts create --accounts frostbite-accounts.toml

# 4) Preload program
cauldron program load --accounts frostbite-accounts.toml guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest

# 5) Stage input + invoke
cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 50000
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml
```

To create VM + RAM accounts via the on-chain runner:

```
cauldron accounts create --accounts frostbite-accounts.toml --ram-count 1
```

To execute with the correct account ordering:

```
cauldron invoke --accounts frostbite-accounts.toml --instructions 50000
```

For low-latency execution (assumes program + input staged):

```
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 50000
```

To stage input payloads into the VM scratch account before invoking:

```
cauldron input-write --manifest frostbite-model.toml \
  --accounts frostbite-accounts.toml --data input.json
```

If no cluster/rpc override is provided, Cauldron will default to your Solana
CLI config (`json_rpc_url` and `keypair_path`).
