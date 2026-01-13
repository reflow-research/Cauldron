#include "bench_common.h"

#define TAG 0xB001
#define ITERS 32

int main(void) {
    bench_heap_setup();
    fb_print("bench_putchar\n");
    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_putchar('A');
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
