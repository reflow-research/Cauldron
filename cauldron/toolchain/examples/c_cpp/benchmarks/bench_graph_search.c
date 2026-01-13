#include "bench_common.h"

#define TAG 0xB040

int main(void) {
    bench_heap_setup();
    fb_print("bench_graph_search\n");

    if (FB_GRAPH_SEGMENT == 0) {
        fb_print("graph segment disabled\n");
        return 0;
    }

    bench_init_graph();

    int8_t input[4] = {1, 2, 3, 4};
    uint32_t *output = (uint32_t *)fb_malloc(sizeof(uint32_t) * 2);
    if (!output) {
        fb_print("alloc failed\n");
        return 1;
    }
    uint64_t graph_idx = (uint64_t)(FB_GRAPH_SEGMENT - 1u);

    bench_log(TAG, 0, 1);
    (void)fb_graph_search(input, graph_idx, output, 0, 0);
    bench_log(TAG, 1, 1);
    return 0;
}
