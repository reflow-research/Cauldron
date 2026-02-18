"""ModelKit constants and enums."""

ALLOWED_ARCH = {"rv64imac"}
ALLOWED_ENDIANNESS = {"little"}
ALLOWED_SCHEMA_TYPES = {"vector", "time_series", "graph", "custom"}
ALLOWED_QUANT = {"q8", "q4", "f16", "f32", "custom"}
ALLOWED_HEADER_FORMAT = {"none", "rvcd-v1"}
ALLOWED_SEGMENT_KIND = {"scratch", "weights", "input", "output", "custom"}
ALLOWED_SEGMENT_ACCESS = {"ro", "rw", "wo"}
ALLOWED_VALIDATION_MODE = {"minimal", "guest"}
ALLOWED_PROFILE = {"finance-int"}

DTYPE_SIZES = {
    "f32": 4,
    "f16": 2,
    "i32": 4,
    "i16": 2,
    "i8": 1,
    "u32": 4,
    "u8": 1,
}

FBM1_MAGIC = 0x314D4246
ABI_VERSION = 1
# VM header offsets from Frostbite `src/vm/mod.rs` (RVVM layout).
VM_MAGIC_OFFSET = 0
VM_FCSR_OFFSET = 4
VM_REGISTERS_OFFSET = 8
VM_FREGISTERS_OFFSET = 264
VM_PC_OFFSET = 520
VM_INSTR_COUNT_OFFSET = 528
VM_HALTED_OFFSET = 536
VM_EXEC_HINTS_OFFSET = 537
VM_EXIT_CODE_OFFSET = 544
VM_MEMORY_OFFSET = 552

# VM account sizing.
VM_HEADER_SIZE = VM_MEMORY_OFFSET
MMU_VM_HEADER_SIZE = VM_HEADER_SIZE
VM_MEMORY_SIZE = 262_144
VM_ACCOUNT_SIZE_MIN = VM_HEADER_SIZE + VM_MEMORY_SIZE

# Default Frostbite program ID (devnet v0).
DEFAULT_PROGRAM_ID = "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m"

MAX_SEGMENT_BYTES = 0x1000_0000
DEFAULT_SCRATCH_MIN = 262_144
MIN_CONTROL_SIZE = 64
MIN_RESERVED_TAIL = 32

SCALE_KEYS = {"w_scale_q16", "w1_scale_q16", "w2_scale_q16", "w3_scale_q16", "w4_scale_q16"}
