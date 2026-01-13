#include "bench_common.h"

#define TAG 0xB015
#define ITERS 2

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_q8\n");

    size_t n = 4;
    size_t d = 4;
    float *x = (float *)fb_malloc(sizeof(float) * n);
    int8_t *w = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    float *scale = (float *)fb_malloc(sizeof(float) * d);
    float *out = (float *)fb_malloc(sizeof(float) * d);
    if (!x || !w || !scale || !out) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(x, n, 0.1f);
    bench_fill_f32(scale, d, 1.0f);
    bench_fill_i8(w, n * d, 1);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_matmul_q8(out, x, w, scale, n, d);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
