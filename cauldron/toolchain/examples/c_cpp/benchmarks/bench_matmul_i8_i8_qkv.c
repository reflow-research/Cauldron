#include "bench_common.h"

#define TAG 0xB02C

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_i8_i8_qkv\n");

    uint32_t n = 4;
    uint32_t d = 4;
    int8_t *x = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *wq = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int8_t *wk = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int8_t *wv = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int32_t *out_q = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    int32_t *out_k = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    int32_t *out_v = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    fb_row_state_t *state = (fb_row_state_t *)fb_malloc(sizeof(fb_row_state_t));
    if (!x || !wq || !wk || !wv || !out_q || !out_k || !out_v || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(x, n, 1);
    bench_fill_i8(wq, n * d, 1);
    bench_fill_i8(wk, n * d, 1);
    bench_fill_i8(wv, n * d, 1);

    fb_matmul_qkv_cfg_t cfg;
    fb_memset(&cfg, 0, sizeof(cfg));
    cfg.out_q = (uint64_t)(uintptr_t)out_q;
    cfg.out_k = (uint64_t)(uintptr_t)out_k;
    cfg.out_v = (uint64_t)(uintptr_t)out_v;
    cfg.x_ptr = (uint64_t)(uintptr_t)x;
    cfg.wq_ptr = (uint64_t)(uintptr_t)wq;
    cfg.wk_ptr = (uint64_t)(uintptr_t)wk;
    cfg.wv_ptr = (uint64_t)(uintptr_t)wv;
    cfg.wq_scale = 1 << 16;
    cfg.wk_scale = 1 << 16;
    cfg.wv_scale = 1 << 16;
    cfg.n = n;
    cfg.d_q = d;
    cfg.d_k = d;
    cfg.d_v = d;
    cfg.state_ptr = (uint64_t)(uintptr_t)state;

    bench_log(TAG, 0, 1);
    fb_matmul_i8_i8_qkv(&cfg);
    bench_log(TAG, 1, 1);
    return 0;
}
