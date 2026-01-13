# Frostbite Rust Example

This program prints a message, computes a dot product, and returns the dot as its exit code.

This folder also includes a syscall smoke test (`src/bin/syscall_smoke.rs`) that exercises all syscalls (with minimal inputs) plus heap/memcpy helpers.

## Local (fast)

```bash
cd toolchain/examples/rust
source ../../scripts/setup.sh
rustup target add riscv64imac-unknown-none-elf
cargo build --release
frostbite-run target/riscv64imac-unknown-none-elf/release/frostbite-hello
```

### Syscall smoke test (local)

```bash
cd toolchain/examples/rust
source ../../scripts/setup.sh
rustup target add riscv64imac-unknown-none-elf
cargo build --release --bin syscall_smoke
frostbite-run target/riscv64imac-unknown-none-elf/release/syscall_smoke
```

If you build with `--features onchain` or use RAM segments, run with
`frostbite-run --ram-count N` (and `--ram-bytes` if you override RAM size).
For the on-chain syscall smoke build (segment 2 heap), use `--ram-count 2`
even locally. If the program yields (e.g., `fb_yield`), add `--max-tx N` or
`--max-tx 0` to resume until it halts.

## On-chain (local validator)

```bash
# Terminal 1 (repo root)
solana-test-validator

# Terminal 2 (repo root)
./build-and-deploy.sh
solana airdrop 2

# Run the program
cd toolchain/examples/rust
source ../../scripts/setup.sh
frostbite-run-onchain target/riscv64imac-unknown-none-elf/release/frostbite-hello
```

To stop and resume across multiple transactions, add `--max-tx` and use `--vm-save`/`--vm-file`.

### Syscall smoke test (on-chain, RAM accounts)

This uses two mapped RAM accounts: segment 1 for graph data and segment 2 for heap/arb data.

```bash
cd toolchain/examples/rust
source ../../scripts/setup.sh
rustup target add riscv64imac-unknown-none-elf
cargo build --release --bin syscall_smoke --features onchain

frostbite-run-onchain target/riscv64imac-unknown-none-elf/release/syscall_smoke --ram-count 2
```

If you override `--ram-bytes`, update `RAM_BYTES` in `src/bin/syscall_smoke.rs` to match.

By default `frostbite-run-onchain` creates one RAM account. Use `--ram-count 0`
to disable.

If you are not in the Frostbite repo, set `FROSTBITE_PROGRAM_ID` or pass `--program-id`.

## Notes

- `.cargo/config.toml` disables the `c` extension so the same ELF works locally and on-chain.
- `Cargo.toml` uses the shared build script at `toolchain/scripts/frostbite-build.rs` so `main()` works like a normal program.
