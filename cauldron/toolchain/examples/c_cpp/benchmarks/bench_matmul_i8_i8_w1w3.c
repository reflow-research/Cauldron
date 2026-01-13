#include "bench_common.h"

#define TAG 0xB02D

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_i8_i8_w1w3\n");

    uint32_t n = 4;
    uint32_t d = 4;
    int8_t *x = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *w1 = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int8_t *w3 = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int32_t *out_a = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    int32_t *out_b = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    fb_row_state_t *state = (fb_row_state_t *)fb_malloc(sizeof(fb_row_state_t));
    if (!x || !w1 || !w3 || !out_a || !out_b || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(x, n, 1);
    bench_fill_i8(w1, n * d, 1);
    bench_fill_i8(w3, n * d, 1);

    fb_matmul_w1w3_cfg_t cfg;
    fb_memset(&cfg, 0, sizeof(cfg));
    cfg.out_a = (uint64_t)(uintptr_t)out_a;
    cfg.out_b = (uint64_t)(uintptr_t)out_b;
    cfg.x_ptr = (uint64_t)(uintptr_t)x;
    cfg.w1_ptr = (uint64_t)(uintptr_t)w1;
    cfg.w3_ptr = (uint64_t)(uintptr_t)w3;
    cfg.w1_scale = 1 << 16;
    cfg.w3_scale = 1 << 16;
    cfg.n = n;
    cfg.d = d;
    cfg.state_ptr = (uint64_t)(uintptr_t)state;

    bench_log(TAG, 0, 1);
    fb_matmul_i8_i8_w1w3(&cfg);
    bench_log(TAG, 1, 1);
    return 0;
}
