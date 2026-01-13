# Frostbite Toolchain (Standalone)

This directory is self-contained: it includes the C headers, linker script, CRT, helper scripts, and the Rust SDK crate.
You can copy `toolchain/` into another repo and use it without the full Frostbite codebase.

To run programs, you need `frostbite-run` and `frostbite-run-onchain` on your `PATH`.
You can place them in `toolchain/bin` and `setup.sh` will add that to `PATH`.

The VM supports native float and double instructions (RV64IMFD). `fb-cc` targets
`rv64imfd` by default so regular floating-point math works without soft-float.

`fb_malloc` always allocates from RAM (default segment 1). Use
`FB_HEAP_SEGMENT` and `FB_HEAP_SEGMENT_COUNT` to span multiple contiguous RAM
segments. If no RAM accounts are mapped (or `FB_HEAP_SEGMENT=0`), `fb_malloc`
exits with a descriptive error.

`frostbite-run` maps one local RAM segment by default so on-chain builds work
off-chain. Use `--ram-count` or `--ram-bytes` to adjust (or `--ram-count 0` to disable).
If your program yields (via `fb_yield` or resumable syscalls), pass `--max-tx N`
or `--max-tx 0` to auto-resume locally.

## Quick start

```bash
export FROSTBITE_TOOLCHAIN=/path/to/toolchain
source /path/to/toolchain/scripts/setup.sh
# Or to persist PATH changes:
# /path/to/toolchain/scripts/setup.sh --persist

# C/C++
fb-cc hello.c -o hello.elf
frostbite-run hello.elf

# Rust
# In Cargo.toml:
#   frostbite-sdk = { path = "/path/to/toolchain/rust/frostbite-sdk" }
#   build = "/path/to/toolchain/scripts/frostbite-build.rs"
```

## On-chain runner

When you are outside the Frostbite repo, set the program ID explicitly:

```bash
export FROSTBITE_PROGRAM_ID=<FROSTBITE_PROGRAM_PUBKEY>
# or pass --program-id to frostbite-run-onchain
```

Create a VM + RAM accounts and save them for reuse:

```bash
frostbite-run-onchain hello.elf \
  --ram-count 2 --ram-save frostbite_ram_accounts.txt \
  --vm-save frostbite_vm_accounts.txt
```

`--ram-save` records all RAM accounts used (loaded + created).

Resume later (same VM + RAM accounts):

```bash
frostbite-run-onchain --vm-file frostbite_vm_accounts.txt \
  --ram-file frostbite_ram_accounts.txt --instructions 50000
```

By default `frostbite-run-onchain` creates one RAM account. Use `--ram-count 0`
to disable.

## Packaging

From the full repo, you can build a standalone tarball (optionally bundling CLI binaries):

```bash
toolchain/scripts/package-toolchain.sh
```

This writes `frostbite-toolchain.tar.gz` in the current directory.

To build a ZIP (with x86_64 Linux CLI binaries), run:

```bash
toolchain/scripts/package-toolchain-zip.sh
```

This writes `frostbite-toolchain-linux-x86_64.zip` in the current directory.
