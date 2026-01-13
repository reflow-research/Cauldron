#include "bench_common.h"

#define TAG 0xB003

int main(void) {
    bench_heap_setup();
    fb_print("bench_exit\n");
    bench_log(TAG, 0, 0);
    fb_exit(0);
}
