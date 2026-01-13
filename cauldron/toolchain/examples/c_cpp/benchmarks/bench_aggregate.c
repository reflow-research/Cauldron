#include "bench_common.h"

#define TAG 0xB044

int main(void) {
    bench_heap_setup();
    fb_print("bench_aggregate\n");

    if (FB_ARB_SEGMENT == 0) {
        fb_print("arb segment disabled\n");
        return 0;
    }

    bench_init_arb();

    uint8_t *table = (uint8_t *)fb_malloc(32);
    uint8_t *features = (uint8_t *)fb_malloc(32);
    if (!table || !features) {
        fb_print("alloc failed\n");
        return 1;
    }
    uint64_t graph_idx = (uint64_t)(FB_ARB_SEGMENT - 1u);

    bench_log(TAG, 0, 1);
    (void)fb_aggregate(graph_idx, table, features, 4);
    bench_log(TAG, 1, 1);
    return 0;
}
