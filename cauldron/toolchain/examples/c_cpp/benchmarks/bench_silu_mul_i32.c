#include "bench_common.h"

#define TAG 0xB027
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_silu_mul_i32\n");

    size_t n = 16;
    int32_t *a = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    int32_t *b = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    if (!a || !b) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i32(a, n, 1);
    bench_fill_i32(b, n, 2);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_silu_mul_i32(a, b, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
