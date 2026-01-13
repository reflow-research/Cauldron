#include "bench_common.h"

#define TAG 0xB02B

int main(void) {
    bench_heap_setup();
    fb_print("bench_matmul_i8_i8_argmax\n");

    size_t n = 4;
    size_t d = 4;
    int8_t *x = (int8_t *)fb_malloc(sizeof(int8_t) * n);
    int8_t *w = (int8_t *)fb_malloc(sizeof(int8_t) * n * d);
    uint32_t *state = (uint32_t *)fb_malloc(sizeof(uint32_t) * FB_I8_I8_ARGMAX_HEADER_WORDS);
    if (!x || !w || !state) {
        fb_print("alloc failed\n");
        return 1;
    }
    bench_fill_i8(x, n, 1);
    bench_fill_i8(w, n * d, 1);
    fb_memset(state, 0, sizeof(uint32_t) * FB_I8_I8_ARGMAX_HEADER_WORDS);
    state[FB_I8_I8_ARGMAX_MAX_ROWS_WORD] = (uint32_t)d;

    bench_log(TAG, 0, 1);
    (void)fb_matmul_i8_i8_argmax_partial(x, w, (1 << 16), n, d, state);
    bench_log(TAG, 1, 1);
    return 0;
}
