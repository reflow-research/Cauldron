---
name: frostbite-cauldron
description: Build, train, convert, and deploy Frostbite/Cauldron on-chain AI models on Solana, including manifest authoring, guest builds, weight packing/chunking/upload, devnet testing, and on-chain inference workflows. Use when asked about Cauldron CLI, frostbite-modelkit, Frostbite guest programs, or end-to-end on-chain inference setup.
---

# Cauldron (Frostbite ModelKit)

## Scope
- Use Cauldron CLI and SDKs to prepare models and run on-chain inference.
- Keep training off-chain and inference on-chain.
- Prefer devnet unless the user explicitly requests mainnet.

## Standard workflow (CLI)
1. Initialize a project: `cauldron init <dir> --template <template>`
2. Train or export weights with your framework.
3. Convert and pack: `cauldron convert --manifest frostbite-model.toml --input <weights> --pack`
4. Build the guest program: `cauldron build-guest --manifest frostbite-model.toml`
5. Chunk and upload: `cauldron chunk --manifest frostbite-model.toml`, then `cauldron upload --all "weights_chunk*.bin" --cluster devnet`
6. Prepare accounts: `cauldron accounts init --manifest frostbite-model.toml` (or use shared devnet VM/RAM)
7. Invoke inference: `cauldron input-write ...`, `cauldron invoke ...`, `cauldron output ...`

Use `cauldron deploy --upload` when the user wants the combined pipeline.
Use `cauldron validate` and `cauldron show` to sanity-check manifests before uploading.

## Templates and manifests
- Keep the manifest in `frostbite-model.toml`.
- Select a template that matches the model architecture: `linear`, `softmax`, `naive_bayes`, `mlp`, `mlp2`, `mlp3`, `cnn1d`, `tiny_cnn`, `two_tower`, `tree`, or `custom`.
- Use `cauldron schema-hash --update-manifest` for custom schemas.

## Where to look for details
- Open `README.md` for CLI overview, training notes, and weight layout examples.
- Open `CAULDRON.md` for end-to-end flows, options, and devnet shared accounts.
- Open `docs/RUNNING_EXAMPLES.md` for a devnet walkthrough.
- Open `docs/FROSTBITE_MODEL_SPEC.md` for manifest/schema/weights format.
- Open `docs/FROSTBITE_GUEST_CONTRACT.md` for guest ABI, entrypoint, and memory layout.
- Open `sdk/` for JS/TS/Python/Rust usage patterns.
- Open `gatekeeper/README.md` when the user wants the on-chain gatekeeper example.

## Safety and devnet notes
- Start on devnet and treat shared VM/RAM accounts as scratch space.
- Do not store secrets or rely on persistence in shared accounts.
- Use `cauldron invoke --dry-run` or Solana simulation before mainnet.

## Troubleshooting
- Add the RISC-V target when guest builds fail: `rustup target add riscv64imac-unknown-none-elf`.
- Set `FROSTBITE_RUN_ONCHAIN` if the on-chain runner is not found.
- Ensure weights header format matches the upload tool (see `CAULDRON.md`).

## Ask for missing context
- Ask which cluster to target and the RPC URL if not provided.
- Ask which template and schema shapes are required.
- Ask which weights format is available (`json`, `npz`, `npy`, `pt`, `safetensors`).
