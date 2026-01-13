#include "bench_common.h"

#define TAG 0xB01B

int main(void) {
    bench_heap_setup();
    fb_print("bench_argmax_partial\n");

    size_t n = 16;
    float *data = (float *)fb_malloc(sizeof(float) * n);
    fb_argmax_state_t *state = (fb_argmax_state_t *)fb_malloc(sizeof(fb_argmax_state_t));
    if (!data || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_f32(data, n, 0.1f);
    state->cursor = 0;
    state->max_idx = 0;
    state->max_bits = 0;
    state->max_per_call = (uint32_t)n;

    bench_log(TAG, 0, 1);
    (void)fb_argmax_partial(data, n, state);
    bench_log(TAG, 1, 1);
    return 0;
}
