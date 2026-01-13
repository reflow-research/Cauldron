# Frostbite C syscall benchmarks

This directory contains one benchmark per syscall wrapper. Each binary executes
one syscall (with tiny fixed inputs) and logs start/end markers via
`fb_debug_log`.

Build everything:

```bash
make
```

Run locally (instruction count shown by `frostbite-run`):

```bash
make run-local
```

Run on-chain (compute units shown by Solana logs):

```bash
export FROSTBITE_PROGRAM_ID=<PROGRAM_PUBKEY>
make run-onchain
```

By default the benchmarks assume three RAM segments:
- segment 1: heap
- segment 2: graph (for graph_search)
- segment 3: arb (for arb_* / aggregate)

Override RAM count with `RAM_COUNT=<n>`.

Output binaries are written to `out/`.
