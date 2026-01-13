#include "bench_common.h"

#define TAG 0xB043

int main(void) {
    bench_heap_setup();
    fb_print("bench_arb_score\n");

    if (FB_ARB_SEGMENT == 0) {
        fb_print("arb segment disabled\n");
        return 0;
    }

    bench_init_arb();

    uint8_t mask = 0;
    uint64_t graph_idx = (uint64_t)(FB_ARB_SEGMENT - 1u);

    bench_log(TAG, 0, 1);
    (void)fb_arb_score(graph_idx, NULL, 0, &mask);
    bench_log(TAG, 1, 1);
    return 0;
}
