#include "bench_common.h"

#define TAG 0xB042

int main(void) {
    bench_heap_setup();
    fb_print("bench_arb_search\n");

    if (FB_ARB_SEGMENT == 0) {
        fb_print("arb segment disabled\n");
        return 0;
    }

    bench_init_arb();

    uint8_t input_mint[32] = {0};
    uint8_t *output = (uint8_t *)fb_malloc(72);
    if (!output) {
        fb_print("alloc failed\n");
        return 1;
    }
    uint64_t graph_idx = (uint64_t)(FB_ARB_SEGMENT - 1u);

    bench_log(TAG, 0, 1);
    (void)fb_arb_search(input_mint, graph_idx, output, 0, NULL);
    bench_log(TAG, 1, 1);
    return 0;
}
