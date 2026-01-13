#include "bench_common.h"

#define TAG 0xB016

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_q8_partial\n");

    size_t n = 4;
    size_t d = 4;
    float *x = (float *)fb_malloc(sizeof(float) * n);
    int8_t *w = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    float *scale = (float *)fb_malloc(sizeof(float) * d);
    float *out = (float *)fb_malloc(sizeof(float) * d);
    fb_row_state_t *state = (fb_row_state_t *)fb_malloc(sizeof(fb_row_state_t));
    if (!x || !w || !scale || !out || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(x, n, 0.1f);
    bench_fill_f32(scale, d, 1.0f);
    bench_fill_i8(w, n * d, 1);
    state->cursor = 0;
    state->max_rows = (uint32_t)d;

    bench_log(TAG, 0, 1);
    fb_matmul_q8_partial(out, x, w, scale, n, d, state);
    bench_log(TAG, 1, 1);
    return 0;
}
