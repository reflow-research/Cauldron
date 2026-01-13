#include "bench_common.h"

#define TAG 0xB013
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_silu\n");

    size_t n = 8;
    float *data = (float *)fb_malloc(sizeof(float) * n);
    if (!data) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(data, n, -0.5f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_silu(data, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
