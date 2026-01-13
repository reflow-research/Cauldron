#include "bench_common.h"

#define TAG 0xB050

int main(void) {
    bench_heap_setup();
    fb_print("bench_quantum_op\n");

    fb_q16_complex_t *state = (fb_q16_complex_t *)fb_malloc(
        sizeof(fb_q16_complex_t) * FB_QUANTUM_STATE_LEN);
    if (!state) {
        fb_print("alloc failed\n");
        return 1;
    }
    fb_memset(state, 0, sizeof(fb_q16_complex_t) * FB_QUANTUM_STATE_LEN);

    bench_log(TAG, 0, 2);
    fb_quantum_op(FB_QOP_INIT, 0, 0, state);
    (void)fb_quantum_op(FB_QOP_MEASURE, 0, 0, state);
    bench_log(TAG, 1, 2);
    return 0;
}
