#include "bench_common.h"

#define TAG 0xB018
#define ITERS 8

int main(void) {
    bench_heap_setup();
    fb_print("bench_read_f32\n");

    float *value = (float *)fb_malloc(sizeof(float));
    if (!value) {
        fb_print("alloc failed\n");
        return 1;
    }
    *value = 3.5f;

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        (void)fb_read_f32((uint64_t)(uintptr_t)value);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
