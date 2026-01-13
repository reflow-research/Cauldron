#include "bench_common.h"

#define TAG 0xB011
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_rmsnorm\n");

    size_t n = 8;
    float *x = (float *)fb_malloc(sizeof(float) * n);
    float *w = (float *)fb_malloc(sizeof(float) * n);
    float *out = (float *)fb_malloc(sizeof(float) * n);
    if (!x || !w || !out) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(x, n, 0.2f);
    bench_fill_f32(w, n, 1.0f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_rmsnorm(out, x, w, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
