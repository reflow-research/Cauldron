#include "bench_common.h"

#define TAG 0xB030
#define ITERS 8

int main(void) {
    bench_heap_setup();
    fb_print("bench_dot_i8\n");

    size_t n = 32;
    int8_t *a = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *b = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    if (!a || !b) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(a, n, 1);
    bench_fill_i8(b, n, 2);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        (void)fb_dot_i8(a, b, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
