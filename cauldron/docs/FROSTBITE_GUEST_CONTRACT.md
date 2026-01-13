# Frostbite Guest Template Contract v0.1

This document defines the guest-side ABI contract for Frostbite model
templates. It is intended for Rust `no_std` guest programs compiled to
RISC-V and executed by the Frostbite VM.

## 1. Execution model
- ISA: RV64IMAC, little-endian.
- Registers and PC are 64-bit.
- Virtual addresses are 32-bit (u32) with 4-bit segment + 28-bit offset.
- Segment 0 is scratch RAM; segments 1-15 map external accounts.

The guest program runs from a bare-metal entrypoint and is responsible for
reading its input, producing output, and exiting with a status code.

## 2. Memory and addressing

### 2.1 Segment addressing
Virtual addresses are constructed as:

```
vaddr = (segment << 28) | (offset & 0x0FFF_FFFF)
```

- Segment 0: scratch RAM (rw)
- Segments 1-15: mapped accounts (weights, input, output, custom)

All guest pointers are virtual addresses. When calling syscalls that accept
pointers, pass the virtual address (u32 widened to u64).

### 2.2 Scratch sizing
The scratch size is defined by the manifest `abi.scratch_min`. The guest MUST
keep all reads/writes within `[0, scratch_min - reserved_tail)`.

The last `abi.reserved_tail` bytes are reserved for the instruction cache
header and must not be touched.

### 2.3 Stack
The guest sets its own stack pointer (SP). SP MUST be inside scratch RAM and
MUST NOT overlap the reserved tail. Recommended pattern:

```
sp = scratch_min - reserved_tail - stack_guard
```

`stack_guard` SHOULD be at least 4KB.

## 3. Control block ABI

The control block lives at `abi.control_offset` in scratch RAM. Layout is
little-endian and 8-byte aligned.

```
struct FbModelControlV1 {
  u32 magic;        // "FBM1" = 0x314D4246
  u32 abi_version;  // 1
  u32 flags;        // reserved
  u32 status;       // 0=ok, nonzero=error
  u32 input_ptr;    // vaddr (u32)
  u32 input_len;    // bytes
  u32 output_ptr;   // vaddr (u32)
  u32 output_len;   // bytes written
  u32 scratch_ptr;  // optional temp region vaddr
  u32 scratch_len;  // bytes
  u32 user_ptr;     // optional state/config
  u32 user_len;     // bytes
  u64 reserved0;    // future use
}
```

The guest MUST read and validate:
- `magic == "FBM1"`
- `abi_version == 1`
- `input_ptr + input_len` within bounds
- `output_ptr + output_len` within bounds

The guest SHOULD:
- Write `status` before exit (mirrors exit code)
- Update `output_len` with bytes produced

## 4. Optional input header (FBH1)

When `validation.mode = "guest"`, the host prepends an input header to the
input payload. The guest MUST validate it and then treat the remaining bytes
as the actual input payload.

```
struct FbInputHeaderV1 {
  u32 magic;       // "FBH1" = 0x31484246
  u16 version;     // 1
  u16 flags;       // bit0=has_crc32, bit1=has_schema_hash
  u32 header_len;  // 32
  u32 schema_id;   // 0=vector,1=time_series,2=graph,3=custom
  u32 payload_len; // bytes after header
  u32 crc32;       // optional
  u32 schema_hash; // optional 32-bit
  u32 reserved0;   // reserved, set to 0
}
```

Validation rules:
- `magic == "FBH1"` and `version == 1`
- `header_len == 32`
- `payload_len == input_len - header_len`
- If `flags.has_schema_hash`, verify `schema_hash` matches manifest
- If `flags.has_crc32`, verify CRC32 over payload

CRC32 is optional. If the flag is not set, no CRC validation is performed.

If validation fails, set `status` and exit with nonzero code.

## 5. Exit contract

The guest MUST exit with syscall 93 (exit) and the exit code MUST match the
control block `status` field.

Recommended error codes:
- 0: OK
- 1: Invalid control block
- 2: Invalid input header (FBH1)
- 3: Schema mismatch
- 4: Input out of bounds
- 5: Output out of bounds
- 6: Misaligned access
- 7: Internal error

## 6. Syscall usage (stable subset)

Minimum required:
- 93: exit

Optional but recommended:
- 122: debug_log (tagged tracing)
- 123: yield (long-running or chunked compute)

Other syscalls (LLM, graph, quantum) are allowed but not required for the
baseline template contract.

## 7. Rust guest template requirements

The canonical guest template SHOULD:
- Use `#![no_std]` and `#![no_main]`.
- Provide a panic handler that triggers `ebreak`.
- Define `_start` to set SP and jump to `rust_main`.
- Use unaligned loads/stores (`read_unaligned`, `write_unaligned`).
- Treat all vaddr pointers as `u32` widened to `u64`.

Example stack setup (do not hardcode if scratch size differs):
```
#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "C" fn _start() -> ! {
    core::arch::naked_asm!(
        "li sp, 0x3C000",  // example: scratch_min - reserved_tail - guard
        "j rust_main",
    );
}
```

## 8. Schema-specific payload notes

Vector/time-series/graph payload layouts are defined by the SDK helpers and
guest templates. The guest MUST interpret payloads according to the manifest
schema and any custom layout annotations.

## 9. Custom schema notes

For `schema.custom`, the guest MUST:
- Enforce `input_blob_size` and `output_blob_size` bounds.
- Optionally verify `schema_hash32` if present.

Minimal validation is allowed, but the guest should still guard against
out-of-bounds and misalignment.
