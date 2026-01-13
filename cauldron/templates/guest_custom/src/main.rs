//! Custom schema template (raw input/output blobs)
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
        "j {rust_main}",
        stack_ptr = const STACK_PTR,
        rust_main = sym rust_main,
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
const FBH_VERSION: usize = 4;    // u16
const FBH_FLAGS: usize = 6;      // u16
const FBH_HEADER_LEN: usize = 8; // u32
const FBH_SCHEMA_ID: usize = 12; // u32
const FBH_PAYLOAD_LEN: usize = 16; // u32
const FBH_CRC32: usize = 20;      // u32
const FBH_SCHEMA_HASH: usize = 24; // u32

// EXPECTED_SCHEMA_ID provided via config

const FBH_FLAG_HAS_CRC32: u16 = 1 << 0;
const FBH_FLAG_HAS_SCHEMA_HASH: u16 = 1 << 1;

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

#[inline(always)]
unsafe fn sys_exit(code: u32) -> ! {
    core::arch::asm!(
        "ecall",
        in("a0") code,
        in("a7") SYSCALL_EXIT,
        options(noreturn)
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
unsafe fn read_u8(addr: u64) -> u8 {
    (addr as *const u8).read_volatile()
}

#[inline(always)]
unsafe fn read_u16(addr: u64) -> u16 {
    (addr as *const u16).read_volatile()
}

#[inline(always)]
unsafe fn read_u32(addr: u64) -> u32 {
    (addr as *const u32).read_volatile()
}

#[inline(always)]
unsafe fn write_u32(addr: u64, value: u32) {
    (addr as *mut u32).write_volatile(value);
}

#[inline(always)]
unsafe fn write_u8(addr: u64, value: u8) {
    (addr as *mut u8).write_volatile(value);
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

        if INPUT_BLOB_SIZE > INPUT_MAX || payload_len < INPUT_BLOB_SIZE {
            write_u32(ctrl_base + CTRL_STATUS as u64, ERR_INPUT_BOUNDS);
            sys_exit(ERR_INPUT_BOUNDS);
        }

        if OUTPUT_BLOB_SIZE > OUTPUT_MAX {
            write_u32(ctrl_base + CTRL_STATUS as u64, ERR_OUTPUT_BOUNDS);
            sys_exit(ERR_OUTPUT_BOUNDS);
        }

        // Example: compute a simple checksum over the input blob and store it
        // at the start of the output buffer. The remaining output bytes are zeroed.
        let mut sum: u32 = 0;
        let mut i = 0usize;
        while i < INPUT_BLOB_SIZE {
            let b = (payload_ptr + i as u64) as *const u8;
            sum = sum.wrapping_add(unsafe { b.read_volatile() } as u32);
            i += 1;
        }

        let mut o = 0usize;
        while o < OUTPUT_BLOB_SIZE {
            let byte = if o < 4 {
                (sum >> (o * 8)) as u8
            } else {
                0
            };
            write_u8(output_ptr + o as u64, byte);
            o += 1;
        }

        write_u32(ctrl_base + CTRL_OUTPUT_LEN as u64, OUTPUT_BLOB_SIZE as u32);
        write_u32(ctrl_base + CTRL_STATUS as u64, ERR_OK);
        sys_exit(ERR_OK);
    }
}
