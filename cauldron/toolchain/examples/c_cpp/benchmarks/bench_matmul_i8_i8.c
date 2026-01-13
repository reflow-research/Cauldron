#include "bench_common.h"

#define TAG 0xB029
#define ITERS 2

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_i8_i8\n");

    size_t n = 4;
    size_t d = 4;
    int8_t *x = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *w = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int32_t *out = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    if (!x || !w || !out) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(x, n, 1);
    bench_fill_i8(w, n * d, 1);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_matmul_i8_i8(out, x, w, (1 << 16), n, d);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
