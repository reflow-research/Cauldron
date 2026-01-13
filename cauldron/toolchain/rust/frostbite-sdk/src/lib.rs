#![no_std]

// ============================================================================
// Constants and types
// ============================================================================

pub const SYS_PUTCHAR: u64 = 60;
pub const SYS_WRITE: u64 = 64;
pub const SYS_EXIT: u64 = 93;
pub const SYS_YIELD: u64 = 123;

pub const SYS_MATMUL: u64 = 110;
pub const SYS_RMSNORM: u64 = 111;
pub const SYS_SOFTMAX: u64 = 112;
pub const SYS_SILU: u64 = 113;
pub const SYS_ROPE: u64 = 114;
pub const SYS_MATMUL_Q8: u64 = 115;
pub const SYS_ACCUM: u64 = 116;
pub const SYS_READ_F32: u64 = 117;
pub const SYS_WRITE_F32: u64 = 118;
pub const SYS_MEMCPY_F32: u64 = 119;
pub const SYS_MATMUL_Q8_PARTIAL: u64 = 120;
pub const SYS_ARGMAX_PARTIAL: u64 = 121;
pub const SYS_DEBUG_LOG: u64 = 122;

pub const SYS_MATMUL_I8_I32: u64 = 130;
pub const SYS_SOFTMAX_I32: u64 = 131;
pub const SYS_DOT_I32: u64 = 132;
pub const SYS_WEIGHTED_SUM_I32: u64 = 133;
pub const SYS_MATMUL_I8_I32_PARTIAL: u64 = 134;
pub const SYS_ARGMAX_I32_PARTIAL: u64 = 135;
pub const SYS_SOFTMAX_I32_F32: u64 = 136;
pub const SYS_SILU_MUL_I32: u64 = 137;
pub const SYS_RMSNORM_I32: u64 = 138;
pub const SYS_MATMUL_I8_I8: u64 = 139;
pub const SYS_MATMUL_I8_I8_PARTIAL: u64 = 140;
pub const SYS_MATMUL_I8_I8_QKV: u64 = 141;
pub const SYS_MATMUL_I8_I8_W1W3: u64 = 142;
pub const SYS_MATMUL_I8_I8_ARGMAX: u64 = 143;
pub const SYS_MATMUL_I8_I8_W1W3_SILU: u64 = 144;

pub const SYS_DOT_I8: u64 = 7001;
pub const SYS_VEC_ADD_I8: u64 = 7003;
pub const SYS_ACTIVATION: u64 = 7010;

pub const SYS_GRAPH_SEARCH: u64 = 8001;
pub const SYS_GRAPH_SEARCH_ALT: u64 = 8002;
pub const SYS_ARB_SEARCH: u64 = 8005;
pub const SYS_ARB_SCORE: u64 = 8010;
pub const SYS_AGGREGATE: u64 = 8020;

pub const SYS_QUANTUM_OP: u64 = 9000;

pub const Q8_FLAG_PREQUANT: u64 = 1u64 << 63;
pub const Q8_FLAG_TENSOR_SCALE: u64 = 1u64 << 62;
pub const Q8_FLAG_MASK: u64 = Q8_FLAG_PREQUANT | Q8_FLAG_TENSOR_SCALE;

pub const ACT_RELU: i32 = 0;
pub const ACT_SIGMOID: i32 = 1;

pub const QOP_INIT: u32 = 0;
pub const QOP_H: u32 = 1;
pub const QOP_CNOT: u32 = 2;
pub const QOP_MEASURE: u32 = 3;
pub const QOP_RX: u32 = 4;
pub const QOP_RZ: u32 = 5;
pub const QOP_PHASE: u32 = 6;

pub const QUANTUM_NUM_QUBITS: usize = 7;
pub const QUANTUM_STATE_LEN: usize = 1usize << QUANTUM_NUM_QUBITS;

#[inline(always)]
pub const fn align4(n: usize) -> usize {
    (n + 3) & !3
}

#[repr(transparent)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct VmAddr(pub u64);

impl VmAddr {
    pub const fn new(segment: u8, offset: u32) -> Option<Self> {
        if segment <= 15 && (offset as u64) < (1u64 << 28) {
            Some(VmAddr(((segment as u64) << 28) | offset as u64))
        } else {
            None
        }
    }

    pub const fn raw(self) -> u64 {
        self.0
    }

    pub const fn null() -> Self {
        VmAddr(0)
    }

    pub fn from_ptr<T>(ptr: *const T) -> Self {
        VmAddr(ptr as u64)
    }

    pub fn from_mut_ptr<T>(ptr: *mut T) -> Self {
        VmAddr(ptr as u64)
    }

    pub fn from_ref<T>(r: &T) -> Self {
        VmAddr(r as *const T as u64)
    }

    pub fn from_mut<T>(r: &mut T) -> Self {
        VmAddr(r as *mut T as u64)
    }

    pub fn from_slice<T>(s: &[T]) -> Self {
        VmAddr(s.as_ptr() as u64)
    }

    pub fn from_mut_slice<T>(s: &mut [T]) -> Self {
        VmAddr(s.as_mut_ptr() as u64)
    }
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct Q16Complex {
    pub re: i32,
    pub im: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct RowState {
    pub cursor: u32,
    pub max_rows: u32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct YieldState {
    pub flag: u32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct ArgmaxState {
    pub cursor: u32,
    pub max_idx: u32,
    pub max_bits: u32,
    pub max_per_call: u32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct ArgmaxI32State {
    pub cursor: u32,
    pub max_idx: u32,
    pub max_val: i32,
    pub max_per_call: u32,
}

pub const I8_I8_ARGMAX_CURSOR_WORD: usize = 0;
pub const I8_I8_ARGMAX_MAX_IDX_WORD: usize = 1;
pub const I8_I8_ARGMAX_MAX_VAL_WORD: usize = 2;
pub const I8_I8_ARGMAX_MAX_ROWS_WORD: usize = 3;
pub const I8_I8_ARGMAX_TOPK2_WORD: usize = 4;
pub const I8_I8_ARGMAX_FILLED2_WORD: usize = 5;
pub const I8_I8_ARGMAX_MIN_VAL2_WORD: usize = 6;
pub const I8_I8_ARGMAX_MIN_POS2_WORD: usize = 7;
pub const I8_I8_ARGMAX_SHORT_N2_WORD: usize = 8;
pub const I8_I8_ARGMAX_TOPK1_WORD: usize = 9;
pub const I8_I8_ARGMAX_FILLED1_WORD: usize = 10;
pub const I8_I8_ARGMAX_MIN_VAL1_WORD: usize = 11;
pub const I8_I8_ARGMAX_MIN_POS1_WORD: usize = 12;
pub const I8_I8_ARGMAX_SHORT_N1_WORD: usize = 13;
pub const I8_I8_ARGMAX_STAGE2_WORD: usize = 14;
pub const I8_I8_ARGMAX_FULL_WORD: usize = 15;
pub const I8_I8_ARGMAX_STAGE2_MAX_WORD: usize = 16;
pub const I8_I8_ARGMAX_FULL_MAX_WORD: usize = 17;
pub const I8_I8_ARGMAX_HEADER_WORDS: usize = 18;

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct MatmulQkvConfig {
    pub out_q: u64,
    pub out_k: u64,
    pub out_v: u64,
    pub x_ptr: u64,
    pub wq_ptr: u64,
    pub wk_ptr: u64,
    pub wv_ptr: u64,
    pub wq_scale: u32,
    pub wk_scale: u32,
    pub wv_scale: u32,
    pub n: u32,
    pub d_q: u32,
    pub d_k: u32,
    pub d_v: u32,
    pub _pad0: u32,
    pub state_ptr: u64,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct MatmulW1W3Config {
    pub out_a: u64,
    pub out_b: u64,
    pub x_ptr: u64,
    pub w1_ptr: u64,
    pub w3_ptr: u64,
    pub w1_scale: u32,
    pub w3_scale: u32,
    pub n: u32,
    pub d: u32,
    pub state_ptr: u64,
}

#[repr(C)]
#[derive(Copy, Clone, Debug)]
pub struct MatmulW1W3SiluConfig {
    pub out_ptr: u64,
    pub x_ptr: u64,
    pub w1_ptr: u64,
    pub w3_ptr: u64,
    pub w1_scale: u32,
    pub w3_scale: u32,
    pub n: u32,
    pub d: u32,
    pub state_ptr: u64,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum SdkError {
    BufferTooSmall,
    LengthMismatch,
}

pub type SdkResult<T> = core::result::Result<T, SdkError>;

// ============================================================================
// Raw syscalls (unsafe)
// ============================================================================

pub mod raw {
    use core::arch::asm;

    #[inline(always)]
    pub unsafe fn ecall0(id: u64) -> u64 {
        let mut a0: u64 = 0;
        asm!("ecall", inlateout("a0") a0, in("a7") id, options(nostack));
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall1(id: u64, a0_in: u64) -> u64 {
        let mut a0 = a0_in;
        asm!("ecall", inlateout("a0") a0, in("a7") id, options(nostack));
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall2(id: u64, a0_in: u64, a1: u64) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall3(id: u64, a0_in: u64, a1: u64, a2: u64) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a2") a2,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall4(id: u64, a0_in: u64, a1: u64, a2: u64, a3: u64) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a2") a2,
            in("a3") a3,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall5(id: u64, a0_in: u64, a1: u64, a2: u64, a3: u64, a4: u64) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a2") a2,
            in("a3") a3,
            in("a4") a4,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall6(
        id: u64,
        a0_in: u64,
        a1: u64,
        a2: u64,
        a3: u64,
        a4: u64,
        a5: u64,
    ) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a2") a2,
            in("a3") a3,
            in("a4") a4,
            in("a5") a5,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn ecall7(
        id: u64,
        a0_in: u64,
        a1: u64,
        a2: u64,
        a3: u64,
        a4: u64,
        a5: u64,
        a6: u64,
    ) -> u64 {
        let mut a0 = a0_in;
        asm!(
            "ecall",
            inlateout("a0") a0,
            in("a1") a1,
            in("a2") a2,
            in("a3") a3,
            in("a4") a4,
            in("a5") a5,
            in("a6") a6,
            in("a7") id,
            options(nostack)
        );
        a0
    }

    #[inline(always)]
    pub unsafe fn exit(code: i64, syscall_id: u64) -> ! {
        asm!("ecall", in("a0") code, in("a7") syscall_id, options(noreturn));
    }
}

// ============================================================================
// Safe wrappers
// ============================================================================

#[inline(always)]
fn check_len(actual: usize, required: usize) -> SdkResult<()> {
    if actual < required {
        Err(SdkError::BufferTooSmall)
    } else {
        Ok(())
    }
}

#[inline(always)]
fn check_equal(a: usize, b: usize) -> SdkResult<()> {
    if a != b {
        Err(SdkError::LengthMismatch)
    } else {
        Ok(())
    }
}

/// Exit the VM with the given code.
pub fn exit(code: i64) -> ! {
    unsafe { raw::exit(code, SYS_EXIT) }
}

/// Write bytes to the VM log.
pub fn write(buf: &[u8]) -> usize {
    unsafe { raw::ecall3(SYS_WRITE, 1, buf.as_ptr() as u64, buf.len() as u64) as usize }
}

/// Write a single byte to the VM log.
pub fn putchar(c: u8) {
    unsafe {
        raw::ecall1(SYS_PUTCHAR, c as u64);
    }
}

/// Yield execution. state.flag toggles between 0 and 1.
pub fn yield_now(state: &mut YieldState) {
    unsafe {
        raw::ecall1(SYS_YIELD, VmAddr::from_mut(state).raw());
    }
}

/// Print a UTF-8 string.
pub fn print(s: &str) {
    write(s.as_bytes());
}

/// MATMUL (deprecated): out = W @ x (f32).
pub fn matmul(out: &mut [f32], x: &[f32], w: VmAddr) -> SdkResult<()> {
    let n = x.len();
    let d = out.len();
    unsafe {
        raw::ecall5(
            SYS_MATMUL,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            w.raw(),
            n as u64,
            d as u64,
        );
    }
    Ok(())
}

/// RMSNORM: out = (x / rms) * weight.
pub fn rmsnorm(out: &mut [f32], x: &[f32], weight: &[f32]) -> SdkResult<()> {
    check_equal(out.len(), x.len())?;
    check_equal(out.len(), weight.len())?;
    unsafe {
        raw::ecall4(
            SYS_RMSNORM,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            VmAddr::from_slice(weight).raw(),
            out.len() as u64,
        );
    }
    Ok(())
}

/// SOFTMAX: in-place softmax on f32.
pub fn softmax(data: &mut [f32]) {
    unsafe {
        raw::ecall2(
            SYS_SOFTMAX,
            VmAddr::from_mut_slice(data).raw(),
            data.len() as u64,
        );
    }
}

/// SILU: in-place SiLU on f32.
pub fn silu(data: &mut [f32]) {
    unsafe {
        raw::ecall2(
            SYS_SILU,
            VmAddr::from_mut_slice(data).raw(),
            data.len() as u64,
        );
    }
}

/// ROPE: rotary embeddings on q/k vectors.
pub fn rope(q: &mut [f32], k: &mut [f32], pos: u64, dim: usize, head_size: usize) -> SdkResult<()> {
    check_len(q.len(), dim)?;
    check_len(k.len(), dim)?;
    unsafe {
        raw::ecall5(
            SYS_ROPE,
            VmAddr::from_mut_slice(q).raw(),
            VmAddr::from_mut_slice(k).raw(),
            pos,
            dim as u64,
            head_size as u64,
        );
    }
    Ok(())
}

/// MATMUL_Q8: quantized int8 matmul.
pub fn matmul_q8(
    out: &mut [f32],
    x_ptr: VmAddr,
    w_ptr: VmAddr,
    scale_ptr: VmAddr,
    n: usize,
    flags: u64,
) -> SdkResult<()> {
    let n_flags = (n as u64) | (flags & Q8_FLAG_MASK);
    unsafe {
        raw::ecall6(
            SYS_MATMUL_Q8,
            VmAddr::from_mut_slice(out).raw(),
            x_ptr.raw(),
            w_ptr.raw(),
            scale_ptr.raw(),
            n_flags,
            out.len() as u64,
        );
    }
    Ok(())
}

/// MATMUL_Q8_PARTIAL: resumable rows.
pub fn matmul_q8_partial(
    out: &mut [f32],
    x_ptr: VmAddr,
    w_ptr: VmAddr,
    scale_ptr: VmAddr,
    n: usize,
    flags: u64,
    state: &mut RowState,
) -> SdkResult<()> {
    let n_flags = (n as u64) | (flags & Q8_FLAG_MASK);
    unsafe {
        raw::ecall7(
            SYS_MATMUL_Q8_PARTIAL,
            VmAddr::from_mut_slice(out).raw(),
            x_ptr.raw(),
            w_ptr.raw(),
            scale_ptr.raw(),
            n_flags,
            out.len() as u64,
            VmAddr::from_mut(state).raw(),
        );
    }
    Ok(())
}

/// ACCUM: out += x (f32).
pub fn accum(out: &mut [f32], x: &[f32]) -> SdkResult<()> {
    check_equal(out.len(), x.len())?;
    unsafe {
        raw::ecall3(
            SYS_ACCUM,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            out.len() as u64,
        );
    }
    Ok(())
}

/// READ_F32: read a float from any VM address.
pub fn read_f32(addr: VmAddr) -> f32 {
    let bits = unsafe { raw::ecall1(SYS_READ_F32, addr.raw()) as u32 };
    f32::from_bits(bits)
}

/// WRITE_F32: write a float to any VM address.
pub fn write_f32(addr: VmAddr, value: f32) {
    unsafe {
        raw::ecall2(SYS_WRITE_F32, addr.raw(), value.to_bits() as u64);
    }
}

/// MEMCPY_F32: copy f32 array between VM addresses.
pub fn memcpy_f32(dst: VmAddr, src: VmAddr, count: usize) {
    unsafe {
        raw::ecall3(SYS_MEMCPY_F32, dst.raw(), src.raw(), count as u64);
    }
}

/// ARGMAX_PARTIAL: resumable argmax over f32.
pub fn argmax_partial(data: &[f32], state: &mut ArgmaxState) -> u32 {
    unsafe {
        raw::ecall3(
            SYS_ARGMAX_PARTIAL,
            VmAddr::from_slice(data).raw(),
            data.len() as u64,
            VmAddr::from_mut(state).raw(),
        ) as u32
    }
}

/// DEBUG_LOG: emit a tagged debug log.
pub fn debug_log(tag: u64, a: u64, b: u64, c: u64, d: u64) {
    unsafe {
        raw::ecall5(SYS_DEBUG_LOG, tag, a, b, c, d);
    }
}

/// MATMUL_I8_I32: int8 weights, i32 activations.
pub fn matmul_i8_i32(out: &mut [i32], x: &[i32], w: VmAddr, scale_q16: i32) -> SdkResult<()> {
    let n = x.len();
    let d = out.len();
    unsafe {
        raw::ecall6(
            SYS_MATMUL_I8_I32,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            w.raw(),
            scale_q16 as u64,
            n as u64,
            d as u64,
        );
    }
    Ok(())
}

/// MATMUL_I8_I32_PARTIAL: resumable rows.
pub fn matmul_i8_i32_partial(
    out: &mut [i32],
    x: &[i32],
    w: VmAddr,
    scale_q16: i32,
    state: &mut RowState,
) -> SdkResult<()> {
    let n = x.len();
    let d = out.len();
    unsafe {
        raw::ecall7(
            SYS_MATMUL_I8_I32_PARTIAL,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            w.raw(),
            scale_q16 as u64,
            n as u64,
            d as u64,
            VmAddr::from_mut(state).raw(),
        );
    }
    Ok(())
}

/// SOFTMAX_I32: Q16 softmax on i32.
pub fn softmax_i32(data: &mut [i32]) {
    unsafe {
        raw::ecall2(
            SYS_SOFTMAX_I32,
            VmAddr::from_mut_slice(data).raw(),
            data.len() as u64,
        );
    }
}

/// DOT_I32: dot(a, b) >> shift.
pub fn dot_i32(a: &[i32], b: &[i32], shift: u32) -> SdkResult<i64> {
    check_equal(a.len(), b.len())?;
    let res = unsafe {
        raw::ecall4(
            SYS_DOT_I32,
            VmAddr::from_slice(a).raw(),
            VmAddr::from_slice(b).raw(),
            a.len() as u64,
            shift as u64,
        )
    };
    Ok(res as i64)
}

/// WEIGHTED_SUM_I32: out[i] += (weight * src[i]) >> shift.
pub fn weighted_sum_i32(out: &mut [i32], src: &[i32], weight: i32, shift: u32) -> SdkResult<()> {
    check_equal(out.len(), src.len())?;
    unsafe {
        raw::ecall5(
            SYS_WEIGHTED_SUM_I32,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(src).raw(),
            weight as u64,
            out.len() as u64,
            shift as u64,
        );
    }
    Ok(())
}

/// ARGMAX_I32_PARTIAL: resumable argmax over i32.
pub fn argmax_i32_partial(data: &[i32], state: &mut ArgmaxI32State) -> u32 {
    unsafe {
        raw::ecall3(
            SYS_ARGMAX_I32_PARTIAL,
            VmAddr::from_slice(data).raw(),
            data.len() as u64,
            VmAddr::from_mut(state).raw(),
        ) as u32
    }
}

/// SOFTMAX_I32_F32: i32 softmax using f32 math.
pub fn softmax_i32_f32(data: &mut [i32]) {
    unsafe {
        raw::ecall2(
            SYS_SOFTMAX_I32_F32,
            VmAddr::from_mut_slice(data).raw(),
            data.len() as u64,
        );
    }
}

/// SILU_MUL_I32: gate SiLU multiply (Q16).
pub fn silu_mul_i32(hb: &mut [i32], hb2: &[i32]) -> SdkResult<()> {
    check_equal(hb.len(), hb2.len())?;
    unsafe {
        raw::ecall3(
            SYS_SILU_MUL_I32,
            VmAddr::from_mut_slice(hb).raw(),
            VmAddr::from_slice(hb2).raw(),
            hb.len() as u64,
        );
    }
    Ok(())
}

/// RMSNORM_I32: RMSNorm for Q16 i32.
pub fn rmsnorm_i32(out: &mut [i32], x: &[i32], weight_addr: VmAddr) -> SdkResult<()> {
    check_equal(out.len(), x.len())?;
    unsafe {
        raw::ecall4(
            SYS_RMSNORM_I32,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(x).raw(),
            weight_addr.raw(),
            out.len() as u64,
        );
    }
    Ok(())
}

/// MATMUL_I8_I8: int8 weights and prequant buffer.
pub fn matmul_i8_i8(
    out: &mut [i32],
    prequant: &[u8],
    n: usize,
    w: VmAddr,
    w_scale_q16: i32,
) -> SdkResult<()> {
    check_len(prequant.len(), align4(n) + 4)?;
    unsafe {
        raw::ecall6(
            SYS_MATMUL_I8_I8,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(prequant).raw(),
            w.raw(),
            w_scale_q16 as u64,
            n as u64,
            out.len() as u64,
        );
    }
    Ok(())
}

/// MATMUL_I8_I8_PARTIAL: resumable rows.
pub fn matmul_i8_i8_partial(
    out: &mut [i32],
    prequant: &[u8],
    n: usize,
    w: VmAddr,
    w_scale_q16: i32,
    state: &mut RowState,
) -> SdkResult<()> {
    check_len(prequant.len(), align4(n) + 4)?;
    unsafe {
        raw::ecall7(
            SYS_MATMUL_I8_I8_PARTIAL,
            VmAddr::from_mut_slice(out).raw(),
            VmAddr::from_slice(prequant).raw(),
            w.raw(),
            w_scale_q16 as u64,
            n as u64,
            out.len() as u64,
            VmAddr::from_mut(state).raw(),
        );
    }
    Ok(())
}

/// MATMUL_I8_I8_ARGMAX_PARTIAL: resumable argmax over logits.
pub fn matmul_i8_i8_argmax_partial(
    prequant: &[u8],
    n: usize,
    w: VmAddr,
    w_scale_q16: i32,
    d: usize,
    state_words: &mut [u32],
) -> SdkResult<u32> {
    check_len(prequant.len(), align4(n) + 4)?;
    check_len(state_words.len(), I8_I8_ARGMAX_HEADER_WORDS)?;
    let res = unsafe {
        raw::ecall6(
            SYS_MATMUL_I8_I8_ARGMAX,
            VmAddr::from_slice(prequant).raw(),
            w.raw(),
            w_scale_q16 as u64,
            n as u64,
            d as u64,
            VmAddr::from_mut_slice(state_words).raw(),
        )
    };
    Ok(res as u32)
}

/// MATMUL_I8_I8_QKV: fused Q/K/V matmul.
pub fn matmul_i8_i8_qkv(cfg: &MatmulQkvConfig) {
    unsafe {
        raw::ecall1(SYS_MATMUL_I8_I8_QKV, VmAddr::from_ref(cfg).raw());
    }
}

/// MATMUL_I8_I8_W1W3: fused W1/W3 matmul.
pub fn matmul_i8_i8_w1w3(cfg: &MatmulW1W3Config) {
    unsafe {
        raw::ecall1(SYS_MATMUL_I8_I8_W1W3, VmAddr::from_ref(cfg).raw());
    }
}

/// MATMUL_I8_I8_W1W3_SILU: fused W1/W3 matmul + SiLU.
pub fn matmul_i8_i8_w1w3_silu(cfg: &MatmulW1W3SiluConfig) {
    unsafe {
        raw::ecall1(SYS_MATMUL_I8_I8_W1W3_SILU, VmAddr::from_ref(cfg).raw());
    }
}

/// DOT_I8: dot product of int8 vectors.
pub fn dot_i8(a: &[i8], b: &[i8]) -> SdkResult<i32> {
    check_equal(a.len(), b.len())?;
    let res = unsafe {
        raw::ecall3(
            SYS_DOT_I8,
            VmAddr::from_slice(a).raw(),
            VmAddr::from_slice(b).raw(),
            a.len() as u64,
        )
    };
    Ok(res as i32)
}

/// VEC_ADD_I8: dst[i] += src[i].
pub fn vec_add_i8(dst: &mut [i8], src: &[i8]) -> SdkResult<()> {
    check_equal(dst.len(), src.len())?;
    unsafe {
        raw::ecall3(
            SYS_VEC_ADD_I8,
            VmAddr::from_mut_slice(dst).raw(),
            VmAddr::from_slice(src).raw(),
            dst.len() as u64,
        );
    }
    Ok(())
}

/// ACTIVATION: apply activation in-place.
pub fn activation(data: &mut [i8], act_type: i32) {
    unsafe {
        raw::ecall3(
            SYS_ACTIVATION,
            VmAddr::from_mut_slice(data).raw(),
            data.len() as u64,
            act_type as u64,
        );
    }
}

/// GRAPH_SEARCH (8001/8002): graph edge search.
pub fn graph_search(input: VmAddr, graph_idx: u64, output: VmAddr, min_score: i32, alt: bool) -> u32 {
    let id = if alt { SYS_GRAPH_SEARCH_ALT } else { SYS_GRAPH_SEARCH };
    unsafe { raw::ecall4(id, input.raw(), graph_idx, output.raw(), min_score as u64) as u32 }
}

/// ARB_SEARCH: arbitrage search in graph.
pub fn arb_search(
    input_mint: VmAddr,
    graph_idx: u64,
    output: VmAddr,
    min_amount: u64,
    mask_ptr: VmAddr,
) -> u32 {
    unsafe {
        raw::ecall5(
            SYS_ARB_SEARCH,
            input_mint.raw(),
            graph_idx,
            output.raw(),
            min_amount,
            mask_ptr.raw(),
        ) as u32
    }
}

/// ARB_SCORE: score edges and write mask.
pub fn arb_score(graph_idx: u64, weights: VmAddr, threshold: u64, mask_ptr: VmAddr) -> u32 {
    unsafe {
        raw::ecall4(
            SYS_ARB_SCORE,
            graph_idx,
            weights.raw(),
            threshold,
            mask_ptr.raw(),
        ) as u32
    }
}

/// AGGREGATE: GNN message passing.
pub fn aggregate(graph_idx: u64, table_ptr: VmAddr, features_ptr: VmAddr, max_nodes: u64) -> u32 {
    unsafe {
        raw::ecall4(
            SYS_AGGREGATE,
            graph_idx,
            table_ptr.raw(),
            features_ptr.raw(),
            max_nodes,
        ) as u32
    }
}

/// QUANTUM_OP: 7-qubit state ops (Q16.16 complex).
pub fn quantum_op(op: u32, target: u32, control: u32, state: &mut [Q16Complex]) -> SdkResult<u32> {
    check_len(state.len(), QUANTUM_STATE_LEN)?;
    let res = unsafe {
        raw::ecall4(
            SYS_QUANTUM_OP,
            op as u64,
            target as u64,
            control as u64,
            VmAddr::from_mut_slice(state).raw(),
        )
    };
    Ok(res as u32)
}
