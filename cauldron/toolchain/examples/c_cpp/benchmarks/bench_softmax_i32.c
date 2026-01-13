#include "bench_common.h"

#define TAG 0xB022
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_softmax_i32\n");

    size_t n = 8;
    int32_t *data = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    if (!data) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i32(data, n, 1);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_softmax_i32(data, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
