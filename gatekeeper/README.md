# Gatekeeper (Devnet v0)

Minimal on-chain gatekeeper that reads Frostbite VM output from scratch and
fails the transaction if a threshold is not met.

## Build + deploy

```
cd gatekeeper
# Solana toolchain:
cargo build-bpf   # or cargo build-sbf (newer toolchain)
solana program deploy target/deploy/frostbite_gatekeeper.so
```

Use the deployed program ID with the JS gatekeeper example:

```
node sdk/js/run_gatekeeper.js \
  --manifest path/to/frostbite-model.toml \
  --accounts path/to/frostbite-accounts.toml \
  --gatekeeper-program-id <GATEKEEPER_ID> \
  --threshold 0
```

## Instruction format

`gatekeeper` expects:

- bytes 0..4: `control_offset` (u32 LE)
- bytes 4..8: `threshold` (i32 LE)
- bytes 8..12: `output_index` (u32 LE, optional)

Accounts:
- [signer] authority
- [read] VM account (scratch)
