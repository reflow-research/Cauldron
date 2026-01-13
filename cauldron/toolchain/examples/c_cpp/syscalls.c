#include "frostbite.h"

#include <stdint.h>
#include <stddef.h>

#ifndef FB_HEAP_SEGMENT
#define FB_HEAP_SEGMENT 1
#endif

#ifndef FB_HEAP_OFFSET
#define FB_HEAP_OFFSET 0
#endif

#ifndef FB_RAM_BYTES
#define FB_RAM_BYTES (4u * 1024u * 1024u)
#endif

#ifndef FB_HEAP_SEGMENT_COUNT
#define FB_HEAP_SEGMENT_COUNT 1
#endif

#ifndef FB_GRAPH_SEGMENT
#define FB_GRAPH_SEGMENT 0
#endif

#ifndef FB_ARB_SEGMENT
#define FB_ARB_SEGMENT FB_HEAP_SEGMENT
#endif

static int failures = 0;

static void check(int cond, const char *msg) {
    if (!cond) {
        fb_print("FAIL: %s\n", msg);
        failures++;
    }
}

static void check_i32(const char *msg, int32_t got, int32_t expect) {
    if (got != expect) {
        fb_print("FAIL: %s (got %d, expected %d)\n", msg, got, expect);
        failures++;
    }
}

static void check_u32(const char *msg, uint32_t got, uint32_t expect) {
    if (got != expect) {
        fb_print("FAIL: %s (got %u, expected %u)\n", msg, got, expect);
        failures++;
    }
}

static void check_f32_bits(const char *msg, float got, float expect) {
    union {
        float f;
        uint32_t u;
    } a, b;
    a.f = got;
    b.f = expect;
    check_u32(msg, a.u, b.u);
}

static void heap_setup(void) {
    fb_heap_init_segments(FB_HEAP_SEGMENT, FB_HEAP_SEGMENT_COUNT,
                          FB_HEAP_OFFSET, FB_RAM_BYTES);
}

static void test_system(void) {
    const char *msg = "syscall smoke: system\n";
    long written = fb_write(msg, fb_strlen(msg));
    check((size_t)written == fb_strlen(msg), "fb_write length");
    fb_putchar('O');
    fb_putchar('K');
    fb_putchar('\n');
}

static void test_memory(void) {
    uint8_t *buf = (uint8_t *)fb_malloc(16);
    uint8_t *buf2 = (uint8_t *)fb_malloc(16);
    check(buf != NULL, "fb_malloc buf");
    check(buf2 != NULL, "fb_malloc buf2");

    if (buf && buf2) {
        fb_memset(buf, 0x5a, 16);
        for (size_t i = 0; i < 16; i++) {
            check(buf[i] == 0x5a, "fb_memset value");
        }

        fb_memcpy(buf2, buf, 16);
        for (size_t i = 0; i < 16; i++) {
            check(buf2[i] == 0x5a, "fb_memcpy value");
        }
    }

    uint8_t *alias = (uint8_t *)malloc(8);
    uint8_t *alias2 = (uint8_t *)malloc(8);
    check(alias != NULL, "malloc alias");
    check(alias2 != NULL, "malloc alias2");
    if (alias && alias2) {
        memset(alias, 0x11, 8);
        memcpy(alias2, alias, 8);
        for (size_t i = 0; i < 8; i++) {
            check(alias2[i] == 0x11, "memcpy alias value");
        }
    }

    float *f = (float *)fb_malloc(sizeof(float));
    if (f) {
        fb_write_f32((uint64_t)f, 3.5f);
        float got = fb_read_f32((uint64_t)f);
        check_f32_bits("read/write f32", got, 3.5f);
    } else {
        check(0, "fb_malloc f32");
    }

    float *src = (float *)fb_malloc(sizeof(float) * 3);
    float *dst = (float *)fb_malloc(sizeof(float) * 3);
    if (src && dst) {
        src[0] = 1.0f;
        src[1] = 2.0f;
        src[2] = 3.0f;
        fb_memcpy_f32((uint64_t)dst, (uint64_t)src, 3);
        check_f32_bits("memcpy_f32[0]", dst[0], 1.0f);
        check_f32_bits("memcpy_f32[1]", dst[1], 2.0f);
        check_f32_bits("memcpy_f32[2]", dst[2], 3.0f);
    } else {
        check(0, "fb_malloc f32 arrays");
    }

    float *accum = (float *)fb_malloc(sizeof(float) * 3);
    float *inc = (float *)fb_malloc(sizeof(float) * 3);
    if (accum && inc) {
        accum[0] = 1.0f;
        accum[1] = 2.0f;
        accum[2] = 3.0f;
        inc[0] = 1.0f;
        inc[1] = 1.0f;
        inc[2] = 1.0f;
        fb_accum(accum, inc, 3);
        check_f32_bits("accum[0]", accum[0], 2.0f);
        check_f32_bits("accum[1]", accum[1], 3.0f);
        check_f32_bits("accum[2]", accum[2], 4.0f);
    } else {
        check(0, "fb_malloc accum");
    }
}

static void test_ai(void) {
    int8_t a[] = {1, 2, 3, 4};
    int8_t b[] = {4, 3, 2, 1};
    int32_t dot = fb_dot_i8(a, b, 4);
    check_i32("dot_i8", dot, 20);

    int8_t dst[] = {1, 1, 1, 1};
    fb_vec_add_i8(dst, b, 4);
    check_i32("vec_add_i8[0]", dst[0], 5);
    check_i32("vec_add_i8[1]", dst[1], 4);
    check_i32("vec_add_i8[2]", dst[2], 3);
    check_i32("vec_add_i8[3]", dst[3], 2);

    int8_t act[] = {-1, 2, -3, 4};
    fb_activation(act, 4, FB_ACT_RELU);
    check_i32("activation[0]", act[0], 0);
    check_i32("activation[1]", act[1], 2);
    check_i32("activation[2]", act[2], 0);
    check_i32("activation[3]", act[3], 4);
}

static void test_llm(void) {
    fb_row_state_t row_state = {0, 0};
    float dummy = 0.0f;
    fb_matmul(&dummy, &dummy, &dummy, 0, 0);
    fb_rmsnorm(&dummy, &dummy, &dummy, 0);
    fb_softmax(&dummy, 0);
    fb_silu(&dummy, 0);
    fb_rope(&dummy, &dummy, 0, 0, 1);
    fb_matmul_q8(&dummy, &dummy, (const int8_t *)&dummy, &dummy, 0, 0);
    fb_matmul_q8_partial(&dummy, &dummy, (const int8_t *)&dummy, &dummy, 0, 0, &row_state);

    fb_argmax_state_t argmax_state = {0, 0, 0, 0};
    fb_argmax_partial(&dummy, 0, &argmax_state);

    fb_debug_log(0x1234, 1, 2, 3, 4);

    int32_t ai[] = {1, 2, 3, 4};
    int32_t bi[] = {1, 1, 1, 1};
    int64_t dot = fb_dot_i32(ai, bi, 4, 0);
    check_i32("dot_i32", (int32_t)dot, 10);

    int32_t weighted_out[] = {1, 1, 1};
    int32_t weighted_src[] = {2, 2, 2};
    fb_weighted_sum_i32(weighted_out, weighted_src, 2, 3, 1);
    check_i32("weighted_sum[0]", weighted_out[0], 3);
    check_i32("weighted_sum[1]", weighted_out[1], 3);
    check_i32("weighted_sum[2]", weighted_out[2], 3);

    fb_softmax_i32(ai, 0);

    fb_matmul_i8_i32(ai, ai, (const int8_t *)ai, 1 << 16, 0, 0);
    fb_matmul_i8_i32_partial(ai, ai, (const int8_t *)ai, 1 << 16, 0, 0, &row_state);

    fb_argmax_i32_state_t argmax_i32_state = {0, 0, 0, 0};
    fb_argmax_i32_partial(ai, 0, &argmax_i32_state);

    fb_softmax_i32_f32(ai, 0);
    fb_silu_mul_i32(ai, bi, 0);
    fb_rmsnorm_i32(ai, ai, 0, 0);

    fb_matmul_i8_i8(ai, &dummy, (const int8_t *)&dummy, 1 << 16, 0, 0);
    fb_matmul_i8_i8_partial(ai, &dummy, (const int8_t *)&dummy, 1 << 16, 0, 0, &row_state);

    uint32_t argmax_state_words[FB_I8_I8_ARGMAX_HEADER_WORDS] = {0};
    fb_matmul_i8_i8_argmax_partial(&dummy, (const int8_t *)&dummy, 1 << 16, 0, 0, argmax_state_words);

    fb_matmul_qkv_cfg_t qkv_cfg = {0};
    qkv_cfg.state_ptr = (uint64_t)&row_state;
    fb_matmul_i8_i8_qkv(&qkv_cfg);

    fb_matmul_w1w3_cfg_t w1w3_cfg = {0};
    w1w3_cfg.state_ptr = (uint64_t)&row_state;
    fb_matmul_i8_i8_w1w3(&w1w3_cfg);

    fb_matmul_w1w3_silu_cfg_t w1w3_silu_cfg = {0};
    w1w3_silu_cfg.state_ptr = (uint64_t)&row_state;
    fb_matmul_i8_i8_w1w3_silu(&w1w3_silu_cfg);
}

static void test_quantum(void) {
    fb_q16_complex_t *state = (fb_q16_complex_t *)fb_malloc(sizeof(fb_q16_complex_t) * FB_QUANTUM_STATE_LEN);
    if (!state) {
        check(0, "fb_malloc quantum state");
        return;
    }

    fb_memset(state, 0, sizeof(fb_q16_complex_t) * FB_QUANTUM_STATE_LEN);
    fb_quantum_op(FB_QOP_INIT, 0, 0, state);
    int meas = fb_quantum_op(FB_QOP_MEASURE, 0, 0, state);
    check(meas == 0 || meas == 1, "quantum measure range");
}

#if FB_ONCHAIN
static void init_graph_segment(uint32_t segment) {
    uint8_t *base = (uint8_t *)(uintptr_t)FB_SEGMENT_ADDR(segment, 0);
    uint32_t *u32 = (uint32_t *)base;
    u32[0] = 0x48505247; /* GRPH */
    u32[1] = 1;          /* num_edges */
    u32[2] = 4;          /* dim */
    u32[3] = 0;          /* padding */

    uint32_t *target = (uint32_t *)(base + 16);
    *target = 7;
    int8_t *weights = (int8_t *)(base + 20);
    weights[0] = 1;
    weights[1] = 1;
    weights[2] = 1;
    weights[3] = 1;
}

static void init_arb_segment(uint32_t segment) {
    uint8_t *base = (uint8_t *)(uintptr_t)FB_SEGMENT_ADDR(segment, 0);
    fb_memset(base, 0, 64);
    base[16] = 0; /* version */
    base[17] = 0; /* num_edges (u16) */
    base[18] = 0;
}

static void test_graph(void) {
    if (FB_GRAPH_SEGMENT == 0) {
        return;
    }

    init_graph_segment(FB_GRAPH_SEGMENT);

    int8_t input[4] = {1, 2, 3, 4};
    uint32_t output[2] = {0, 0};
    uint64_t graph_idx = (uint64_t)(FB_GRAPH_SEGMENT - 1u);

    uint32_t hits = fb_graph_search(input, graph_idx, output, 0, 0);
    check_u32("graph_search hits", hits, 1);
    check_u32("graph_search node", output[0], 7);

    uint32_t hits_alt = fb_graph_search(input, graph_idx, output, 0, 1);
    check_u32("graph_search_alt hits", hits_alt, 1);
}

static void test_arb(void) {
    if (FB_ARB_SEGMENT == 0) {
        return;
    }

    init_arb_segment(FB_ARB_SEGMENT);

    uint8_t input_mint[32] = {0};
    uint8_t output[72] = {0};
    uint8_t mask = 0;
    uint64_t graph_idx = (uint64_t)(FB_ARB_SEGMENT - 1u);

    uint32_t matches = fb_arb_search(input_mint, graph_idx, output, 0, NULL);
    check_u32("arb_search matches", matches, 0);

    uint32_t passing = fb_arb_score(graph_idx, NULL, 0, &mask);
    check_u32("arb_score passing", passing, 0);

    uint8_t table[32] = {0};
    uint8_t features[32] = {0};
    uint32_t agg = fb_aggregate(graph_idx, table, features, 4);
    check_u32("aggregate nodes", agg, 0);
}
#endif

int main(void) {
    heap_setup();

    fb_print("Frostbite syscall smoke (C)\n");

    fb_print("test_system\n");
    test_system();
    fb_print("test_memory\n");
    test_memory();
    fb_print("test_ai\n");
    test_ai();
    fb_print("test_llm\n");
    test_llm();
    fb_print("test_quantum\n");
    test_quantum();

#if FB_ONCHAIN
    test_graph();
    test_arb();

    fb_yield_state_t ys = {0};
    fb_yield(&ys);
#endif

    if (failures != 0) {
        fb_print("FAILURES: %d\n", failures);
        return 1;
    }

    fb_print("OK\n");
    return 0;
}
