#include "bench_common.h"

#define TAG 0xB017
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_accum\n");

    size_t n = 16;
    float *a = (float *)fb_malloc(sizeof(float) * n);
    float *b = (float *)fb_malloc(sizeof(float) * n);
    if (!a || !b) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(a, n, 1.0f);
    bench_fill_f32(b, n, 0.5f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_accum(a, b, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
