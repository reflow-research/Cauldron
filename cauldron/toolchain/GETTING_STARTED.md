# Frostbite VM - Getting Started

Frostbite is a RISC-V virtual machine (RV64IM) that runs on the Solana blockchain. This guide will help you compile and run your first program.

> **Note:** The toolchain compiles to RV64IM (no compressed instructions) for compatibility with the local CLI runner. On-chain execution supports RV64IMAC with compressed instructions.

## Requirements

- **LLVM/Clang** with RISC-V support
- **LLD** linker
- **Rust** (for the local runner)

### Quick Install (Ubuntu/Debian)

```bash
sudo apt install clang lld llvm
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

## Setup

1. Clone the repository and set up the toolchain:

```bash
git clone https://github.com/reflow-xyz/frostbite
cd frostbite
source toolchain/scripts/setup.sh
# Or to persist PATH changes:
# toolchain/scripts/setup.sh --persist
```

This will:
- Check for required tools
- Build the `frostbite-run` local executor
- Set up environment variables

## Your First Program

### 1. Create a C program

Create `hello.c`:

```c
#include "frostbite.h"

int main(void) {
    fb_print("Hello from Frostbite!\n");
    return 42;
}
```

### 2. Compile it

```bash
fb-cc hello.c -o hello.elf
```

### 3. Run it locally

```bash
frostbite-run hello.elf
```

Output:
```
Format: ELF (entry=0x0, 1 segment(s), 184 bytes)
Running (max 1000000 instructions)...
Program exited with code: 42
```

If your program uses RAM segments (including `fb_malloc`), use
`frostbite-run --ram-count N` to map RAM locally. The default is one RAM
segment; use `--ram-count 0` to disable or `--ram-bytes` to match on-chain
RAM size. If your program uses `fb_yield` or resumable syscalls, pass
`--max-tx N` (or `--max-tx 0` for unlimited) to keep resuming until it halts.

The VM supports native float and double instructions (RV64IMFD). `fb-cc`
targets `rv64imfd` so regular floating-point math executes directly in the VM.

## Using the SDK

### C Header

Include `frostbite.h` for syscall wrappers:

```c
#include "frostbite.h"

int main(void) {
    // Print to Solana logs
    fb_print("Hello!\n");

    // Dot product acceleration
    int8_t a[] = {1, 2, 3, 4};
    int8_t b[] = {1, 1, 1, 1};
    int32_t dot = fb_dot_i8(a, b, 4);  // = 10

    // Exit
    return 0;
}
```

### Available Syscalls

See [SYSCALLS.md](SYSCALLS.md) for the complete syscall reference.

**System:**
- `fb_exit(code)` - Exit program
- `fb_write(buf, len)` - Write to log
- `fb_print(fmt, ...)` - Print formatted log (printf-style)
- `fb_print_str(str)` - Print string without format parsing
- `fb_putchar(c)` - Print character
- `fb_heap_init(base, size)` - Initialize heap (mapped segment or scratch)
- `fb_malloc(bytes)` - Simple bump allocator
- `fb_memcpy(dst, src, len)` - Byte copy helper
- `fb_memset(dst, val, len)` - Byte fill helper

**AI/ML Accelerators:**
- `fb_dot_i8(a, b, len)` - Int8 dot product
- `fb_vec_add_i8(dst, src, len)` - Vector addition
- `fb_activation(data, len, type)` - Apply activation (ReLU/Sigmoid)

**LLM Accelerators:**
- `fb_rmsnorm(out, x, weight, size)` - RMS normalization
- `fb_softmax(data, size)` - Softmax
- `fb_silu(data, size)` - SiLU activation
- `fb_rope(q, k, pos, head_dim, n_heads)` - Rotary embeddings
- `fb_matmul_q8(...)` - Quantized matrix multiplication

**Quantum Simulation:**
- `fb_quantum_op(op, target, control, state, n_qubits)` - Quantum gates

## Compiler Options

```bash
fb-cc [options] source.c ... -o output.elf

Options:
  -o FILE    Output file
  -c         Compile only (produce .o)
  -S         Produce assembly
  -v         Verbose output
  -I DIR     Add include directory
  -O0/1/2/3  Optimization level
  -g         Debug symbols
```

## Memory Layout

```
0x00000000 - 0x0003FFFF : RAM (256KB)
  0x00000000 : Code (.text)
  ...        : Data (.data, .rodata)
  ...        : BSS (.bss)
  ...        : Heap (grows up)
  0x0003FFF0 : Stack (grows down)
```

## Mapped RAM (MMU)

On-chain, you can attach additional Solana accounts as RAM segments. The
first mapped account is segment 1, the next is segment 2, and so on.

In C:
- Use `FB_SEGMENT_ADDR(segment, offset)` to form a pointer into a RAM segment.
- `fb_malloc` always allocates from RAM (default segment 1). Override with
  `-DFB_HEAP_SEGMENT=<seg> -DFB_HEAP_SEGMENT_COUNT=<n>` to span contiguous
  segments, or call `fb_heap_init_segments(...)`. If no RAM accounts are mapped
  (or `FB_HEAP_SEGMENT=0`), `fb_malloc` exits with a descriptive error.

In Rust:
- Use `VmAddr::new(segment, offset)` for addresses in mapped RAM.

`frostbite-run-onchain` prints the segment mapping for any `--ram`/`--ram-file`
accounts so you can match segments in your program.

By default `frostbite-run-onchain` creates one RAM account. Use `--ram-count 0`
to disable.

## Running on Solana

To run your program on Solana:

1. Deploy the Frostbite program
2. Create a VM account
3. Upload your ELF binary
4. Execute transactions

The CLI runner handles these steps automatically:

```bash
# Terminal 1
solana-test-validator

# Terminal 2 (repo root)
./build-and-deploy.sh
solana airdrop 2

# Run on-chain (create VM + RAM accounts, save for reuse)
frostbite-run-onchain hello.elf \
  --ram-count 2 --ram-save frostbite_ram_accounts.txt \
  --vm-save frostbite_vm_accounts.txt

# Resume later (same VM + RAM accounts)
frostbite-run-onchain --vm-file frostbite_vm_accounts.txt \
  --ram-file frostbite_ram_accounts.txt --instructions 50000
```

If your program uses `fb_malloc`, pass RAM accounts via `--ram-count` (or
`--ram-file`) so the heap has a mapped segment.

See the `examples/` directory for client code examples. When running `frostbite-run-onchain` outside the repo, set `FROSTBITE_PROGRAM_ID` or pass `--program-id`.

## Troubleshooting

### "clang: error: unknown target"

Install LLVM with RISC-V support:
```bash
sudo apt install clang-15 lld-15 llvm-15
```

### "Program did not halt"

Your program may be in an infinite loop or exceeding the instruction limit.
Increase the limit:
```bash
frostbite-run program.elf 10000000
```

### "MemoryOutOfBounds"

Your program accessed memory outside the 256KB RAM region.
Check array bounds and pointer arithmetic.

## Next Steps

- Read [SYSCALLS.md](SYSCALLS.md) for the full syscall reference
- Check `examples/` for more complex examples
- See the LLM inference example in `examples/run_inference.rs`
