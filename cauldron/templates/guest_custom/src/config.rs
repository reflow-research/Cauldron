//! Auto-generated config constants (patched by Cauldron).

pub const CONTROL_OFFSET: usize = 0x0000;
pub const INPUT_MAX: usize = 4096;
pub const OUTPUT_MAX: usize = 256;

pub const SCRATCH_MIN: usize = 262_144;
pub const RESERVED_TAIL: usize = 32;
pub const STACK_GUARD: usize = 0x4000;
pub const STACK_PTR: usize = SCRATCH_MIN - RESERVED_TAIL - STACK_GUARD;

pub const INPUT_BLOB_SIZE: usize = 1024;
pub const OUTPUT_BLOB_SIZE: usize = 16;

pub const EXPECTED_SCHEMA_HASH: u32 = 0;
pub const EXPECTED_SCHEMA_ID: u32 = 3;
