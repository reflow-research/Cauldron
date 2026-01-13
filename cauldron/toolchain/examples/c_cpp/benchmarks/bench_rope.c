#include "bench_common.h"

#define TAG 0xB014
#define ITERS 2

int main(void) {
    bench_heap_setup();
    fb_print("bench_rope\n");

    int dim = 8;
    int head = 8;
    float *q = (float *)fb_malloc(sizeof(float) * dim);
    float *k = (float *)fb_malloc(sizeof(float) * dim);
    if (!q || !k) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(q, dim, 0.1f);
    bench_fill_f32(k, dim, 0.2f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_rope(q, k, 0, dim, head);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
