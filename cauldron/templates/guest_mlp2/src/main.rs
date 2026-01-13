//! MLP-2 template (vector -> hidden1 -> hidden2 -> score), integer-only
#![no_std]
#![no_main]

use core::panic::PanicInfo;

mod config;
use config::*;

// ============================================================================
//  Panic / Entry
// ============================================================================

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    unsafe { core::arch::asm!("ebreak") };
    loop {}
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "C" fn _start() -> ! {
    // Stack pointer configured via config.rs
    core::arch::naked_asm!(
        "li sp, {stack_ptr}",
        "j rust_main",
        stack_ptr = const STACK_PTR,
    );
}

// ============================================================================
//  Control block layout
// ============================================================================

const FBM1_MAGIC: u32 = 0x314D_4246; // "FBM1"

const CTRL_MAGIC: usize = 0;
const CTRL_ABI_VERSION: usize = 4;
const CTRL_STATUS: usize = 12;
const CTRL_INPUT_PTR: usize = 16;
const CTRL_INPUT_LEN: usize = 20;
const CTRL_OUTPUT_PTR: usize = 24;
const CTRL_OUTPUT_LEN: usize = 28;

// ============================================================================
//  Optional FBH1 input header
// ============================================================================

const FBH1_MAGIC: u32 = 0x3148_4246; // "FBH1"
const FBH1_HEADER_LEN: usize = 32;

const FBH_MAGIC: usize = 0;
const FBH_VERSION: usize = 4;     // u16
const FBH_FLAGS: usize = 6;       // u16
const FBH_HEADER_LEN: usize = 8;  // u32
const FBH_SCHEMA_ID: usize = 12;  // u32
const FBH_PAYLOAD_LEN: usize = 16; // u32
const FBH_CRC32: usize = 20;      // u32
const FBH_SCHEMA_HASH: usize = 24; // u32

const FBH_FLAG_HAS_CRC32: u16 = 1 << 0;
const FBH_FLAG_HAS_SCHEMA_HASH: u16 = 1 << 1;

// EXPECTED_SCHEMA_ID provided via config

// ============================================================================
//  Error codes
// ============================================================================

const ERR_OK: u32 = 0;
const ERR_CTRL: u32 = 1;
const ERR_INPUT_HEADER: u32 = 2;
const ERR_SCHEMA: u32 = 3;
const ERR_INPUT_BOUNDS: u32 = 4;
const ERR_OUTPUT_BOUNDS: u32 = 5;

// ============================================================================
//  Syscalls
// ============================================================================

const SYSCALL_EXIT: u32 = 93;
const SYSCALL_MATMUL_I8_I32: u32 = 130;

#[inline(always)]
unsafe fn sys_exit(code: u32) -> ! {
    core::arch::asm!(
        "ecall",
        in("a0") code,
        in("a7") SYSCALL_EXIT,
        options(noreturn)
    );
}

#[inline(always)]
unsafe fn syscall6(id: u32, a0: u64, a1: u64, a2: u64, a3: u64, a4: u64, a5: u64) {
    core::arch::asm!(
        "ecall",
        in("a0") a0,
        in("a1") a1,
        in("a2") a2,
        in("a3") a3,
        in("a4") a4,
        in("a5") a5,
        in("a7") id,
        lateout("a0") _,
        options(nostack)
    );
}

#[inline(always)]
unsafe fn matmul_i8_i32(out: u64, x: u64, w: u64, scale_q16: i32, n: usize, d: usize) {
    syscall6(
        SYSCALL_MATMUL_I8_I32,
        out,
        x,
        w,
        scale_q16 as u64,
        n as u64,
        d as u64,
    );
}

// ============================================================================
//  Helpers
// ============================================================================

#[inline(always)]
fn scratch_addr(offset: usize) -> u64 {
    offset as u64
}

#[inline(always)]
fn vaddr(segment: u32, offset: usize) -> u64 {
    ((segment as u64) << 28) | (offset as u64)
}

#[inline(always)]
unsafe fn read_u8(addr: u64) -> u8 {
    (addr as *const u8).read_unaligned()
}

#[inline(always)]
unsafe fn read_u16(addr: u64) -> u16 {
    (addr as *const u16).read_unaligned()
}

#[inline(always)]
unsafe fn read_u32(addr: u64) -> u32 {
    (addr as *const u32).read_unaligned()
}

#[inline(always)]
unsafe fn read_i32(addr: u64) -> i32 {
    read_u32(addr) as i32
}

#[inline(always)]
unsafe fn write_u32(addr: u64, value: u32) {
    (addr as *mut u32).write_unaligned(value);
}

#[inline(always)]
unsafe fn write_i32(addr: u64, value: i32) {
    write_u32(addr, value as u32);
}

#[inline(always)]
fn relu_i32(x: i32) -> i32 {
    if x > 0 { x } else { 0 }
}

#[inline(always)]
fn crc32(payload_ptr: u64, payload_len: usize) -> u32 {
    let mut crc: u32 = 0xFFFF_FFFF;
    let mut i = 0usize;
    while i < payload_len {
        let byte = unsafe { read_u8(payload_ptr + i as u64) } as u32;
        crc ^= byte;
        let mut j = 0u8;
        while j < 8 {
            if (crc & 1) != 0 {
                crc = (crc >> 1) ^ 0xEDB8_8320;
            } else {
                crc >>= 1;
            }
            j += 1;
        }
        i += 1;
    }
    !crc
}

#[inline(always)]
unsafe fn parse_input_header(input_ptr: u64, input_len: usize) -> Result<(u64, usize), u32> {
    if input_len < FBH1_HEADER_LEN {
        return Ok((input_ptr, input_len));
    }

    let magic = read_u32(input_ptr + FBH_MAGIC as u64);
    if magic != FBH1_MAGIC {
        return Ok((input_ptr, input_len));
    }

    let version = read_u16(input_ptr + FBH_VERSION as u64);
    let flags = read_u16(input_ptr + FBH_FLAGS as u64);
    let header_len = read_u32(input_ptr + FBH_HEADER_LEN as u64) as usize;
    let schema_id = read_u32(input_ptr + FBH_SCHEMA_ID as u64);
    let payload_len = read_u32(input_ptr + FBH_PAYLOAD_LEN as u64) as usize;
    let crc_expected = read_u32(input_ptr + FBH_CRC32 as u64);
    let schema_hash = read_u32(input_ptr + FBH_SCHEMA_HASH as u64);

    if version != 1 || header_len != FBH1_HEADER_LEN {
        return Err(ERR_INPUT_HEADER);
    }

    if schema_id != EXPECTED_SCHEMA_ID {
        return Err(ERR_SCHEMA);
    }

    if payload_len != input_len - header_len {
        return Err(ERR_INPUT_HEADER);
    }

    let payload_ptr = input_ptr + header_len as u64;

    if (flags & FBH_FLAG_HAS_SCHEMA_HASH) != 0 {
        if EXPECTED_SCHEMA_HASH == 0 || schema_hash != EXPECTED_SCHEMA_HASH {
            return Err(ERR_SCHEMA);
        }
    }

    if (flags & FBH_FLAG_HAS_CRC32) != 0 {
        let crc = crc32(payload_ptr, payload_len);
        if crc != crc_expected {
            return Err(ERR_INPUT_HEADER);
        }
    }

    Ok((payload_ptr, payload_len))
}

// ============================================================================
//  Entry
// ============================================================================

#[no_mangle]
pub extern "C" fn rust_main() -> ! {
    unsafe {
        let ctrl_base = scratch_addr(CONTROL_OFFSET);
        let magic = read_u32(ctrl_base + CTRL_MAGIC as u64);
        let abi_version = read_u32(ctrl_base + CTRL_ABI_VERSION as u64);
        if magic != FBM1_MAGIC || abi_version != 1 {
            write_u32(ctrl_base + CTRL_STATUS as u64, ERR_CTRL);
            sys_exit(ERR_CTRL);
        }

        let input_ptr = read_u32(ctrl_base + CTRL_INPUT_PTR as u64) as u64;
        let input_len = read_u32(ctrl_base + CTRL_INPUT_LEN as u64) as usize;
        let output_ptr = read_u32(ctrl_base + CTRL_OUTPUT_PTR as u64) as u64;

        let (payload_ptr, payload_len) = match parse_input_header(input_ptr, input_len) {
            Ok(v) => v,
            Err(code) => {
                write_u32(ctrl_base + CTRL_STATUS as u64, code);
                sys_exit(code);
            }
        };

        let input_bytes = INPUT_DIM * 4;
        if input_bytes > INPUT_MAX || payload_len < input_bytes {
            write_u32(ctrl_base + CTRL_STATUS as u64, ERR_INPUT_BOUNDS);
            sys_exit(ERR_INPUT_BOUNDS);
        }

        let output_bytes = OUTPUT_DIM * 4;
        if output_bytes > OUTPUT_MAX {
            write_u32(ctrl_base + CTRL_STATUS as u64, ERR_OUTPUT_BOUNDS);
            sys_exit(ERR_OUTPUT_BOUNDS);
        }

        let w1_base = WEIGHTS_DATA_OFFSET + WEIGHTS_OFFSET;
        let b1_base = w1_base + INPUT_DIM * HIDDEN_DIM1;
        let w2_base = b1_base + if HAS_BIAS { HIDDEN_DIM1 * 4 } else { 0 };
        let b2_base = w2_base + HIDDEN_DIM1 * HIDDEN_DIM2;
        let w3_base = b2_base + if HAS_BIAS { HIDDEN_DIM2 * 4 } else { 0 };
        let b3_base = w3_base + HIDDEN_DIM2 * OUTPUT_DIM;

        let hidden1_ptr = scratch_addr(HIDDEN1_OFFSET);
        let hidden2_ptr = scratch_addr(HIDDEN2_OFFSET);

        matmul_i8_i32(
            hidden1_ptr,
            payload_ptr,
            vaddr(WEIGHTS_SEG, w1_base),
            W1_SCALE_Q16,
            INPUT_DIM,
            HIDDEN_DIM1,
        );

        let mut h = 0usize;
        while h < HIDDEN_DIM1 {
            let addr = hidden1_ptr + (h * 4) as u64;
            let mut val = read_i32(addr);
            if HAS_BIAS {
                let bias = read_i32(vaddr(WEIGHTS_SEG, b1_base + h * 4));
                val = val.wrapping_add(bias);
            }
            val = relu_i32(val);
            write_i32(addr, val);
            h += 1;
        }

        matmul_i8_i32(
            hidden2_ptr,
            hidden1_ptr,
            vaddr(WEIGHTS_SEG, w2_base),
            W2_SCALE_Q16,
            HIDDEN_DIM1,
            HIDDEN_DIM2,
        );

        let mut h2 = 0usize;
        while h2 < HIDDEN_DIM2 {
            let addr = hidden2_ptr + (h2 * 4) as u64;
            let mut val = read_i32(addr);
            if HAS_BIAS {
                let bias = read_i32(vaddr(WEIGHTS_SEG, b2_base + h2 * 4));
                val = val.wrapping_add(bias);
            }
            val = relu_i32(val);
            write_i32(addr, val);
            h2 += 1;
        }

        matmul_i8_i32(
            output_ptr,
            hidden2_ptr,
            vaddr(WEIGHTS_SEG, w3_base),
            W3_SCALE_Q16,
            HIDDEN_DIM2,
            OUTPUT_DIM,
        );

        if HAS_BIAS {
            let mut o = 0usize;
            while o < OUTPUT_DIM {
                let out_addr = output_ptr + (o * 4) as u64;
                let out_val = read_i32(out_addr);
                let bias = read_i32(vaddr(WEIGHTS_SEG, b3_base + o * 4));
                write_i32(out_addr, out_val.wrapping_add(bias));
                o += 1;
            }
        }

        write_u32(ctrl_base + CTRL_OUTPUT_LEN as u64, output_bytes as u32);
        write_u32(ctrl_base + CTRL_STATUS as u64, ERR_OK);
        sys_exit(ERR_OK);
    }
}
