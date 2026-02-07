# SDK Examples (Devnet v0)

These examples show how to invoke a Frostbite VM, then read the output from the
VM scratch account. Each example expects a populated `frostbite-accounts.toml`
and a manifest with ABI offsets.

Prereqs:
- VM account initialized and present in `frostbite-accounts.toml`
- Weights uploaded (for weights-backed models)
- Input already written via `cauldron input-write`

Invoke sizing note:
- Start with `--instructions 50000` for most templates.
- For `cnn1d` and `tiny_cnn`, prefer `--instructions 10000` with higher
  `--max-tx` to avoid per-transaction CU exhaustion.
- Seeded account files default to fresh restart execution (`--mode fresh`).
  Use resume mode only when persistent runtime state is intentional.

Read-after-invoke note:
- On shared RPC endpoints, query lag can return stale account data briefly.
- Prefer invoke commands that print signatures, confirm as `finalized`, then
  read output.

## JS/TS

```
cd sdk/js
npm install
node run_inference.js --manifest ../../path/to/frostbite-model.toml \
  --accounts ../../path/to/frostbite-accounts.toml --instructions 50000

# Gatekeeper (optional)
See `gatekeeper/README.md` for build/deploy steps.
node run_gatekeeper.js --manifest ../../path/to/frostbite-model.toml \
  --accounts ../../path/to/frostbite-accounts.toml \
  --gatekeeper-program-id <GATEKEEPER_ID> \
  --threshold 0
```

## Python

```
cd sdk/python
pip install solana solders tomli
python run_inference.py --manifest ../../path/to/frostbite-model.toml \
  --accounts ../../path/to/frostbite-accounts.toml --instructions 50000
```

## Rust

```
cd sdk/rust
cargo run -- --manifest ../../path/to/frostbite-model.toml \
  --accounts ../../path/to/frostbite-accounts.toml --instructions 50000
```
