#include "bench_common.h"

#define TAG 0xB01A
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_memcpy_f32\n");

    size_t n = 16;
    float *src = (float *)fb_malloc(sizeof(float) * n);
    float *dst = (float *)fb_malloc(sizeof(float) * n);
    if (!src || !dst) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(src, n, 0.5f);

    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_memcpy_f32((uint64_t)(uintptr_t)dst, (uint64_t)(uintptr_t)src, n);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
