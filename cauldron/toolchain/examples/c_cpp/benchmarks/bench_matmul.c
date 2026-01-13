#include "bench_common.h"

#define TAG 0xB010
#define ITERS 2

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul\n");

    size_t n = 4;
    size_t d = 4;
    float *x = (float *)fb_malloc(sizeof(float) * n);
    float *w = (float *)fb_malloc(sizeof(float) * n * d);
    float *out = (float *)fb_malloc(sizeof(float) * d);
    if (!x || !w || !out) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(x, n, 0.1f);
    bench_fill_f32(w, n * d, 0.2f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_matmul(out, x, w, n, d);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
