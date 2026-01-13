# Running Examples (Localnet)

This is a minimal end-to-end flow for a linear model on localnet. Use it as a
template for other manifests.

## Prereqs
- Localnet running (for example: `solana-test-validator --reset`)
- `frostbite-run-onchain` on PATH or set `FROSTBITE_RUN_ONCHAIN`
- Payer keypair (default: `~/.config/solana/id.json`)
- Frostbite program deployed to localnet (or pass `--program-id`)

Note: keep `abi.entry >= 0x4000` so guest code does not overwrite the VM
header/control block. Templates already default to `0x4000`.

## 1) Create a project

```
cauldron init demo-linear --template linear
cd demo-linear
```

Optional: swap in an example manifest (re-run `build-guest` after copying).

```
cp ../examples/models/linear-liquidity.frostbite-model.toml frostbite-model.toml
```

## 2) Create weights + build the guest

```
python3 - <<'PY'
import json
w = [float(i % 8 - 4) for i in range(64)]
b = [0.25]
json.dump({"w": w, "b": b}, open("weights.json", "w"))
PY

cauldron convert --manifest frostbite-model.toml --input weights.json --pack
cauldron build-guest --manifest frostbite-model.toml
```

## 3) Create VM + RAM accounts

Create a weights keypair (used by `cauldron upload`):

```
solana-keygen new --no-bip39-passphrase -o weights-keypair.json --force
```

Create VM + RAM via the on-chain runner:

```
export FROSTBITE_RUN_ONCHAIN=/path/to/frostbite-run-onchain  # if needed

frostbite-run-onchain guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest \
  --vm-save frostbite_vm_accounts.txt \
  --ram-count 1 \
  --ram-save frostbite_ram_accounts.txt \
  --rpc http://localhost:8899 \
  --keypair ~/.config/solana/id.json \
  --program-id FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m \
  --instructions 1 \
  --no-simulate
```

Then build the accounts file:

```
cauldron accounts init --manifest frostbite-model.toml \
  --vm-file frostbite_vm_accounts.txt \
  --ram-file frostbite_ram_accounts.txt \
  --weights-keypair weights-keypair.json \
  --rpc-url http://localhost:8899 \
  --payer ~/.config/solana/id.json \
  --program-id FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m
```

## 4) Upload weights, stage input, invoke

```
cauldron upload --file weights.bin --accounts frostbite-accounts.toml

python3 - <<'PY'
import json
json.dump(list(range(1, 65)), open("input.json", "w"))
PY

cauldron input-write --manifest frostbite-model.toml --accounts frostbite-accounts.toml --data input.json
cauldron invoke --accounts frostbite-accounts.toml \
  --program-path guest/target/riscv64imac-unknown-none-elf/release/frostbite-guest \
  --instructions 50000
cauldron output --manifest frostbite-model.toml --accounts frostbite-accounts.toml --use-max
```

## Troubleshooting

- Invalid instruction or early halt: verify `abi.entry` is `0x4000` and rebuild
  the guest (`cauldron build-guest`).
- Runner not found: set `FROSTBITE_RUN_ONCHAIN` to the full path.
- Empty output: use `--use-max` with `cauldron output` to read the full buffer.
