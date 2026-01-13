//! Auto-generated config constants (patched by Cauldron).

pub const CONTROL_OFFSET: usize = 0x0000;
pub const INPUT_MAX: usize = 4096;
pub const OUTPUT_MAX: usize = 256;

pub const SCRATCH_MIN: usize = 262_144;
pub const RESERVED_TAIL: usize = 32;
pub const STACK_GUARD: usize = 0x4000;
pub const STACK_PTR: usize = SCRATCH_MIN - RESERVED_TAIL - STACK_GUARD;

pub const INPUT_DIM_A: usize = 64;
pub const INPUT_DIM_B: usize = 64;
pub const EMBED_DIM: usize = 16;
pub const OUTPUT_DIM: usize = 1;

pub const WEIGHTS_SEG: u32 = 1;
pub const WEIGHTS_OFFSET: usize = 0;
pub const WEIGHTS_DATA_OFFSET: usize = 0;

pub const W1_SCALE_Q16: i32 = 65_536;
pub const W2_SCALE_Q16: i32 = 65_536;
pub const HAS_BIAS: bool = true;
pub const DOT_SHIFT: u32 = 16;

pub const EMBED_A_OFFSET: usize = 0x3000;
pub const EMBED_B_OFFSET: usize = 0x3040;

pub const EXPECTED_SCHEMA_HASH: u32 = 0;
pub const EXPECTED_SCHEMA_ID: u32 = 0;
