#include "bench_common.h"

#define TAG 0xB024
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_weighted_sum_i32\n");

    size_t n = 16;
    int32_t *out = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    int32_t *src = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    if (!out || !src) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i32(out, n, 0);
    bench_fill_i32(src, n, 1);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_weighted_sum_i32(out, src, 1 << 16, n, 16);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
