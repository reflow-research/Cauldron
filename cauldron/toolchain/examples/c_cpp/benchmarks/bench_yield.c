#include "bench_common.h"

#define TAG 0xB004
#define ITERS 4

int main(void) {
    bench_heap_setup();
    fb_print("bench_yield (clear)\n");
    fb_yield_state_t state = {1};
    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_yield(&state);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
