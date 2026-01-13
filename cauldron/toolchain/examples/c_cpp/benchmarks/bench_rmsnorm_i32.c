#include "bench_common.h"

#define TAG 0xB028
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_rmsnorm_i32\n");

    size_t n = 8;
    int32_t *x = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    int32_t *w = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    int32_t *out = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    if (!x || !w || !out) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i32(x, n, 1);
    bench_fill_i32(w, n, 1);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_rmsnorm_i32(out, x, (uint64_t)(uintptr_t)w, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
