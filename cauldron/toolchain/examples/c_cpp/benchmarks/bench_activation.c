#include "bench_common.h"

#define TAG 0xB032
#define ITERS 8

int main(void) {
    bench_heap_setup();
    fb_print("bench_activation\n");

    size_t n = 32;
    int8_t *data = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    if (!data) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(data, n, -8);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_activation(data, n, FB_ACT_RELU);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
