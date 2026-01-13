#include "bench_common.h"

#define TAG 0xB02A

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_i8_i8_partial\n");

    size_t n = 4;
    size_t d = 4;
    int8_t *x = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *w = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    int32_t *out = (int32_t *)fb_malloc(sizeof(int32_t) * d);
    fb_row_state_t *state = (fb_row_state_t *)fb_malloc(sizeof(fb_row_state_t));
    if (!x || !w || !out || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(x, n, 1);
    bench_fill_i8(w, n * d, 1);
    state->cursor = 0;
    state->max_rows = (uint32_t)d;

    bench_log(TAG, 0, 1);
    fb_matmul_i8_i8_partial(out, x, w, (1 << 16), n, d, state);
    bench_log(TAG, 1, 1);
    return 0;
}
