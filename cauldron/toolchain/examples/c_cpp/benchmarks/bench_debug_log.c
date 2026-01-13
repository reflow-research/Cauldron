#include "bench_common.h"

#define TAG 0xB005
#define ITERS 8

int main(void) {
    bench_heap_setup();
    fb_print("bench_debug_log\n");
    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_debug_log(TAG, (uint64_t)i, 0, 0, 0);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
