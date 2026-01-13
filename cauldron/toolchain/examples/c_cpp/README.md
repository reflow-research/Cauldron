# Frostbite C/C++ Example

This program prints formatted logs in a loop, computes a dot product, and returns the dot as its exit code.

This folder also includes a syscall smoke test (`syscalls.c`) that exercises all syscalls (with minimal inputs) plus heap/memcpy helpers.

## Local (fast)

```bash
cd toolchain/examples/c_cpp
source ../../scripts/setup.sh
fb-cc hello.c -o hello.elf
frostbite-run hello.elf
```

### Syscall smoke test (local)

```bash
cd toolchain/examples/c_cpp
source ../../scripts/setup.sh
fb-cc syscalls.c -o syscall_smoke.elf
frostbite-run syscall_smoke.elf
```

If you compile with `-DFB_ONCHAIN=1` or use RAM segments, run with
`frostbite-run --ram-count N` (and `--ram-bytes` if you override RAM size).
For the on-chain syscall smoke config (heap in segment 2), use `--ram-count 2`
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
cd toolchain/examples/c_cpp
source ../../scripts/setup.sh
frostbite-run-onchain hello.elf
```

If your program uses `fb_malloc`, pass RAM accounts via `--ram-count`
(or `--ram-file`) so the heap has a mapped segment.

To stop and resume across multiple transactions, add `--max-tx` and use `--vm-save`/`--vm-file`.

### Syscall smoke test (on-chain, RAM accounts)

This uses two mapped RAM accounts: segment 1 for graph data and segment 2 for heap/arb data.

```bash
cd toolchain/examples/c_cpp
source ../../scripts/setup.sh
fb-cc syscalls.c -o syscall_smoke.elf \\
  -DFB_GRAPH_SEGMENT=1 -DFB_HEAP_SEGMENT=2 -DFB_HEAP_OFFSET=128

frostbite-run-onchain syscall_smoke.elf --ram-count 2
```

`fb_malloc` always uses RAM (default segment 1). Use `FB_HEAP_SEGMENT` and
`FB_HEAP_SEGMENT_COUNT` to span multiple contiguous RAM segments. If no RAM
accounts are mapped (or `FB_HEAP_SEGMENT=0`), `fb_malloc` exits with a
descriptive error.

If you override `--ram-bytes`, also define `FB_RAM_BYTES` to match (bytes per RAM account).

If you are not in the Frostbite repo, set `FROSTBITE_PROGRAM_ID` or pass `--program-id`.

## CMake (optional)

```cmake
include(/path/to/frostbite/toolchain/scripts/frostbite.cmake)
frostbite_add_executable(hello hello.c)
```

```bash
cd toolchain/examples/c_cpp
cmake -S . -B build
cmake --build build
```

## Syscall benchmarks

The `benchmarks/` folder contains one benchmark per syscall wrapper, plus a
Makefile that builds into `benchmarks/out/` and can run them locally or on-chain.
