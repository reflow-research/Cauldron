#include "bench_common.h"

#define TAG 0xB019
#define ITERS 8

int main(void) {
    bench_heap_setup();
    fb_print("bench_write_f32\n");

    float *value = (float *)fb_malloc(sizeof(float));
    if (!value) {
        fb_print("alloc failed\n");
        return 1;
    }

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_write_f32((uint64_t)(uintptr_t)value, 2.5f + (float)i);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
