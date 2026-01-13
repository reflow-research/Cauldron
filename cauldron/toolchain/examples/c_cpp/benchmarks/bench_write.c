#include "bench_common.h"

#define TAG 0xB002
#define ITERS 8

int main(void) {
    bench_heap_setup();
    const char *msg = "bench_write\n";
    size_t len = fb_strlen(msg);
    bench_log(TAG, 0, ITERS);
    for (int i = 0; i < ITERS; i++) {
        fb_write(msg, len);
    }
    bench_log(TAG, 1, ITERS);
    return 0;
}
