#![no_std]
#![no_main]

use core::mem;
use core::panic::PanicInfo;
use frostbite_sdk as fb;

extern "C" {
    static __heap_start: u8;
    static __stack_top: u8;
}

#[cfg(feature = "onchain")]
const HEAP_SEGMENT: u8 = 2;
#[cfg(not(feature = "onchain"))]
const HEAP_SEGMENT: u8 = 0;

#[cfg(feature = "onchain")]
const GRAPH_SEGMENT: u8 = 1;
#[cfg(not(feature = "onchain"))]
#[allow(dead_code)]
const GRAPH_SEGMENT: u8 = 0;

#[cfg(feature = "onchain")]
const ARB_SEGMENT: u8 = 2;
#[cfg(not(feature = "onchain"))]
#[allow(dead_code)]
const ARB_SEGMENT: u8 = 0;

const HEAP_OFFSET: usize = 128;
const RAM_BYTES: usize = 4 * 1024 * 1024;

static mut HEAP_PTR: usize = 0;
static mut HEAP_END: usize = 0;

unsafe fn heap_init() {
    if HEAP_SEGMENT == 0 {
        HEAP_PTR = &__heap_start as *const u8 as usize;
        HEAP_END = &__stack_top as *const u8 as usize;
    } else {
        let base = fb::VmAddr::new(HEAP_SEGMENT, HEAP_OFFSET as u32)
            .unwrap_or(fb::VmAddr::null());
        HEAP_PTR = base.raw() as usize;
        HEAP_END = HEAP_PTR + (RAM_BYTES.saturating_sub(HEAP_OFFSET));
    }
}

unsafe fn alloc_bytes(size: usize) -> *mut u8 {
    if size == 0 {
        return core::ptr::null_mut();
    }

    if HEAP_PTR == 0 || HEAP_END == 0 {
        heap_init();
    }

    let size = (size + 7) & !7;
    if HEAP_PTR + size > HEAP_END {
        return core::ptr::null_mut();
    }

    let ptr = HEAP_PTR as *mut u8;
    HEAP_PTR += size;
    ptr
}

unsafe fn alloc_slice<T>(len: usize) -> *mut T {
    let bytes = len.saturating_mul(mem::size_of::<T>());
    alloc_bytes(bytes) as *mut T
}

fn check(cond: bool, msg: &'static str, failures: &mut i32) {
    if !cond {
        fb::print("FAIL: ");
        fb::print(msg);
        fb::print("\n");
        *failures += 1;
    }
}

fn test_system(failures: &mut i32) {
    let msg = "syscall smoke: system\n";
    let written = fb::write(msg.as_bytes());
    check(written == msg.len(), "write length", failures);
    fb::putchar(b'O');
    fb::putchar(b'K');
    fb::putchar(b'\n');
}

fn test_memory(failures: &mut i32) {
    unsafe {
        let buf = alloc_bytes(16);
        let buf2 = alloc_bytes(16);
        check(!buf.is_null(), "alloc buf", failures);
        check(!buf2.is_null(), "alloc buf2", failures);

        if !buf.is_null() && !buf2.is_null() {
            core::ptr::write_bytes(buf, 0x5a, 16);
            for i in 0..16 {
                let v = core::ptr::read(buf.add(i));
                check(v == 0x5a, "memset value", failures);
            }

            core::ptr::copy_nonoverlapping(buf, buf2, 16);
            for i in 0..16 {
                let v = core::ptr::read(buf2.add(i));
                check(v == 0x5a, "memcpy value", failures);
            }
        }

        let f = alloc_slice::<f32>(1);
        check(!f.is_null(), "alloc f32", failures);
        if !f.is_null() {
            fb::write_f32(fb::VmAddr::from_mut_ptr(f), 3.5);
            let got = fb::read_f32(fb::VmAddr::from_ptr(f));
            check(got.to_bits() == 3.5f32.to_bits(), "read/write f32", failures);
        }

        let src = alloc_slice::<f32>(3);
        let dst = alloc_slice::<f32>(3);
        check(!src.is_null() && !dst.is_null(), "alloc f32 arrays", failures);
        if !src.is_null() && !dst.is_null() {
            core::ptr::write(src.add(0), 1.0);
            core::ptr::write(src.add(1), 2.0);
            core::ptr::write(src.add(2), 3.0);

            fb::memcpy_f32(
                fb::VmAddr::from_mut_ptr(dst),
                fb::VmAddr::from_ptr(src),
                3,
            );

            let d0 = core::ptr::read(dst.add(0));
            let d1 = core::ptr::read(dst.add(1));
            let d2 = core::ptr::read(dst.add(2));
            check(d0.to_bits() == 1.0f32.to_bits(), "memcpy_f32[0]", failures);
            check(d1.to_bits() == 2.0f32.to_bits(), "memcpy_f32[1]", failures);
            check(d2.to_bits() == 3.0f32.to_bits(), "memcpy_f32[2]", failures);
        }

        let accum = alloc_slice::<f32>(3);
        let inc = alloc_slice::<f32>(3);
        check(!accum.is_null() && !inc.is_null(), "alloc accum", failures);
        if !accum.is_null() && !inc.is_null() {
            core::ptr::write(accum.add(0), 1.0);
            core::ptr::write(accum.add(1), 2.0);
            core::ptr::write(accum.add(2), 3.0);
            core::ptr::write(inc.add(0), 1.0);
            core::ptr::write(inc.add(1), 1.0);
            core::ptr::write(inc.add(2), 1.0);

            let out = core::slice::from_raw_parts_mut(accum, 3);
            let input = core::slice::from_raw_parts(inc, 3);
            let _ = fb::accum(out, input);

            check(out[0].to_bits() == 2.0f32.to_bits(), "accum[0]", failures);
            check(out[1].to_bits() == 3.0f32.to_bits(), "accum[1]", failures);
            check(out[2].to_bits() == 4.0f32.to_bits(), "accum[2]", failures);
        }
    }
}

fn test_ai(failures: &mut i32) {
    let a: [i8; 4] = [1, 2, 3, 4];
    let b: [i8; 4] = [4, 3, 2, 1];
    let dot = fb::dot_i8(&a, &b).unwrap_or(0);
    check(dot == 20, "dot_i8", failures);

    let mut dst: [i8; 4] = [1, 1, 1, 1];
    let _ = fb::vec_add_i8(&mut dst, &b);
    check(dst[0] == 5, "vec_add_i8[0]", failures);
    check(dst[1] == 4, "vec_add_i8[1]", failures);
    check(dst[2] == 3, "vec_add_i8[2]", failures);
    check(dst[3] == 2, "vec_add_i8[3]", failures);

    let mut act: [i8; 4] = [-1, 2, -3, 4];
    let _ = fb::activation(&mut act, fb::ACT_RELU);
    check(act[0] == 0, "activation[0]", failures);
    check(act[1] == 2, "activation[1]", failures);
    check(act[2] == 0, "activation[2]", failures);
    check(act[3] == 4, "activation[3]", failures);
}

fn test_llm(failures: &mut i32) {
    let mut empty_f32: [f32; 0] = [];
    let mut empty_f32_b: [f32; 0] = [];
    let mut empty_i32: [i32; 0] = [];

    let _ = fb::matmul(&mut empty_f32, &[], fb::VmAddr::null());
    let _ = fb::rmsnorm(&mut empty_f32, &[], &[]);
    let _ = fb::softmax(&mut empty_f32);
    let _ = fb::silu(&mut empty_f32);
    let _ = fb::rope(&mut empty_f32, &mut empty_f32_b, 0, 0, 1);

    let _ = fb::matmul_q8(&mut empty_f32, fb::VmAddr::null(), fb::VmAddr::null(), fb::VmAddr::null(), 0, 0);
    let mut row_state = fb::RowState { cursor: 0, max_rows: 0 };
    let _ = fb::matmul_q8_partial(&mut empty_f32, fb::VmAddr::null(), fb::VmAddr::null(), fb::VmAddr::null(), 0, 0, &mut row_state);

    let mut argmax_state = fb::ArgmaxState { cursor: 0, max_idx: 0, max_bits: 0, max_per_call: 0 };
    let _ = fb::argmax_partial(&empty_f32, &mut argmax_state);

    fb::debug_log(0x1234, 1, 2, 3, 4);

    let a: [i32; 4] = [1, 2, 3, 4];
    let b: [i32; 4] = [1, 1, 1, 1];
    let dot = fb::dot_i32(&a, &b, 0).unwrap_or(0);
    check(dot == 10, "dot_i32", failures);

    let mut out: [i32; 3] = [1, 1, 1];
    let src: [i32; 3] = [2, 2, 2];
    let _ = fb::weighted_sum_i32(&mut out, &src, 2, 1);
    check(out[0] == 3, "weighted_sum[0]", failures);
    check(out[1] == 3, "weighted_sum[1]", failures);
    check(out[2] == 3, "weighted_sum[2]", failures);

    let _ = fb::softmax_i32(&mut empty_i32);
    let _ = fb::softmax_i32_f32(&mut empty_i32);

    let _ = fb::matmul_i8_i32(&mut empty_i32, &[], fb::VmAddr::null(), 1 << 16);
    let mut argmax_i32_state = fb::ArgmaxI32State { cursor: 0, max_idx: 0, max_val: 0, max_per_call: 0 };
    let _ = fb::argmax_i32_partial(&empty_i32, &mut argmax_i32_state);

    let _ = fb::silu_mul_i32(&mut empty_i32, &[]);
    let _ = fb::rmsnorm_i32(&mut empty_i32, &[], fb::VmAddr::null());

    let prequant = [0u8; 4];
    let _ = fb::matmul_i8_i8(&mut empty_i32, &prequant, 0, fb::VmAddr::null(), 1 << 16);
    let _ = fb::matmul_i8_i8_partial(&mut empty_i32, &prequant, 0, fb::VmAddr::null(), 1 << 16, &mut row_state);

    let mut state_words = [0u32; fb::I8_I8_ARGMAX_HEADER_WORDS];
    let _ = fb::matmul_i8_i8_argmax_partial(&prequant, 0, fb::VmAddr::null(), 1 << 16, 0, &mut state_words);

    let mut qkv_state = fb::RowState { cursor: 0, max_rows: 0 };
    let qkv_cfg = fb::MatmulQkvConfig {
        out_q: 0,
        out_k: 0,
        out_v: 0,
        x_ptr: 0,
        wq_ptr: 0,
        wk_ptr: 0,
        wv_ptr: 0,
        wq_scale: 0,
        wk_scale: 0,
        wv_scale: 0,
        n: 0,
        d_q: 0,
        d_k: 0,
        d_v: 0,
        _pad0: 0,
        state_ptr: fb::VmAddr::from_mut(&mut qkv_state).raw(),
    };
    fb::matmul_i8_i8_qkv(&qkv_cfg);

    let mut w1w3_state = fb::RowState { cursor: 0, max_rows: 0 };
    let w1w3_cfg = fb::MatmulW1W3Config {
        out_a: 0,
        out_b: 0,
        x_ptr: 0,
        w1_ptr: 0,
        w3_ptr: 0,
        w1_scale: 0,
        w3_scale: 0,
        n: 0,
        d: 0,
        state_ptr: fb::VmAddr::from_mut(&mut w1w3_state).raw(),
    };
    fb::matmul_i8_i8_w1w3(&w1w3_cfg);

    let mut w1w3_silu_state = fb::RowState { cursor: 0, max_rows: 0 };
    let w1w3_silu_cfg = fb::MatmulW1W3SiluConfig {
        out_ptr: 0,
        x_ptr: 0,
        w1_ptr: 0,
        w3_ptr: 0,
        w1_scale: 0,
        w3_scale: 0,
        n: 0,
        d: 0,
        state_ptr: fb::VmAddr::from_mut(&mut w1w3_silu_state).raw(),
    };
    fb::matmul_i8_i8_w1w3_silu(&w1w3_silu_cfg);
}

fn test_quantum(failures: &mut i32) {
    let mut state = [fb::Q16Complex { re: 0, im: 0 }; fb::QUANTUM_STATE_LEN];
    let _ = fb::quantum_op(fb::QOP_INIT, 0, 0, &mut state);
    let meas = fb::quantum_op(fb::QOP_MEASURE, 0, 0, &mut state).unwrap_or(0);
    check(meas == 0 || meas == 1, "quantum measure", failures);
}

#[cfg(feature = "onchain")]
#[repr(C)]
struct GraphHeader {
    magic: u32,
    num_edges: u32,
    dim: u32,
    _pad: u32,
}

#[cfg(feature = "onchain")]
unsafe fn init_graph_segment() {
    let base = fb::VmAddr::new(GRAPH_SEGMENT, 0).unwrap();
    let header_ptr = base.raw() as *mut GraphHeader;
    core::ptr::write(
        header_ptr,
        GraphHeader {
            magic: 0x48505247,
            num_edges: 1,
            dim: 4,
            _pad: 0,
        },
    );

    let edge_base = base.raw() as usize + mem::size_of::<GraphHeader>();
    let target_ptr = edge_base as *mut u32;
    core::ptr::write(target_ptr, 7);
    let weights_ptr = (edge_base + 4) as *mut i8;
    core::ptr::write(weights_ptr.add(0), 1);
    core::ptr::write(weights_ptr.add(1), 1);
    core::ptr::write(weights_ptr.add(2), 1);
    core::ptr::write(weights_ptr.add(3), 1);
}

#[cfg(feature = "onchain")]
unsafe fn init_arb_segment() {
    let base = fb::VmAddr::new(ARB_SEGMENT, 0).unwrap();
    core::ptr::write_bytes(base.raw() as *mut u8, 0, 64);
    let header_ptr = base.raw() as *mut u8;
    core::ptr::write(header_ptr.add(16), 0u8);
    core::ptr::write(header_ptr.add(17), 0u8);
    core::ptr::write(header_ptr.add(18), 0u8);
}

#[cfg(feature = "onchain")]
fn test_graph(failures: &mut i32) {
    if GRAPH_SEGMENT == 0 {
        return;
    }

    unsafe {
        init_graph_segment();
    }

    let input: [i8; 4] = [1, 2, 3, 4];
    let mut output: [u32; 2] = [0, 0];
    let graph_idx = (GRAPH_SEGMENT - 1) as u64;

    let hits = fb::graph_search(
        fb::VmAddr::from_slice(&input),
        graph_idx,
        fb::VmAddr::from_mut_slice(&mut output),
        0,
        false,
    );
    check(hits == 1, "graph_search hits", failures);
    check(output[0] == 7, "graph_search node", failures);

    let hits_alt = fb::graph_search(
        fb::VmAddr::from_slice(&input),
        graph_idx,
        fb::VmAddr::from_mut_slice(&mut output),
        0,
        true,
    );
    check(hits_alt == 1, "graph_search_alt hits", failures);
}

#[cfg(feature = "onchain")]
fn test_arb(failures: &mut i32) {
    if ARB_SEGMENT == 0 {
        return;
    }

    unsafe {
        init_arb_segment();
    }

    let input_mint = [0u8; 32];
    let mut output = [0u8; 72];
    let mut mask = [0u8; 1];
    let graph_idx = (ARB_SEGMENT - 1) as u64;

    let matches = fb::arb_search(
        fb::VmAddr::from_slice(&input_mint),
        graph_idx,
        fb::VmAddr::from_mut_slice(&mut output),
        0,
        fb::VmAddr::null(),
    );
    check(matches == 0, "arb_search matches", failures);

    let passing = fb::arb_score(
        graph_idx,
        fb::VmAddr::null(),
        0,
        fb::VmAddr::from_mut_slice(&mut mask),
    );
    check(passing == 0, "arb_score passing", failures);

    let mut table = [0u8; 32];
    let mut features = [0u8; 32];
    let agg = fb::aggregate(
        graph_idx,
        fb::VmAddr::from_mut_slice(&mut table),
        fb::VmAddr::from_mut_slice(&mut features),
        4,
    );
    check(agg == 0, "aggregate nodes", failures);
}

#[no_mangle]
pub extern "C" fn main() -> i32 {
    unsafe {
        heap_init();
    }

    fb::print("Frostbite syscall smoke (Rust)\n");

    let mut failures = 0;
    test_system(&mut failures);
    test_memory(&mut failures);
    test_ai(&mut failures);
    test_llm(&mut failures);
    test_quantum(&mut failures);

    #[cfg(feature = "onchain")]
    {
        test_graph(&mut failures);
        test_arb(&mut failures);
        let mut ys = fb::YieldState { flag: 0 };
        fb::yield_now(&mut ys);
    }

    if failures != 0 {
        fb::print("FAILURES\n");
        return 1;
    }

    fb::print("OK\n");
    0
}

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    fb::print("panic\n");
    fb::exit(1);
}
