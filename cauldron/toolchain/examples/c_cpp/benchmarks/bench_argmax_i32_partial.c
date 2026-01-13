#include "bench_common.h"

#define TAG 0xB025

int main(void) {
    bench_heap_setup();
    fb_print("bench_argmax_i32_partial\n");

    size_t n = 16;
    int32_t *data = (int32_t *)fb_malloc(sizeof(int32_t) * n);
    fb_argmax_i32_state_t *state = (fb_argmax_i32_state_t *)fb_malloc(sizeof(fb_argmax_i32_state_t));
    if (!data || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i32(data, n, 1);
    state->cursor = 0;
    state->max_idx = 0;
    state->max_val = 0;
    state->max_per_call = (uint32_t)n;

    bench_log(TAG, 0, 1);
    (void)fb_argmax_i32_partial(data, n, state);
    bench_log(TAG, 1, 1);
    return 0;
}
