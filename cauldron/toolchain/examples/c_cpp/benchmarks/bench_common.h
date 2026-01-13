#ifndef FB_BENCH_COMMON_H
#define FB_BENCH_COMMON_H

#include "frostbite.h"

#include <stdint.h>
#include <stddef.h>

#ifndef FB_HEAP_SEGMENT
#define FB_HEAP_SEGMENT 1
#endif

#ifndef FB_HEAP_SEGMENT_COUNT
#define FB_HEAP_SEGMENT_COUNT 1
#endif

#ifndef FB_HEAP_OFFSET
#define FB_HEAP_OFFSET 0
#endif

#ifndef FB_RAM_BYTES
#define FB_RAM_BYTES (4u * 1024u * 1024u)
#endif

#ifndef FB_GRAPH_SEGMENT
#define FB_GRAPH_SEGMENT 2
#endif

#ifndef FB_ARB_SEGMENT
#define FB_ARB_SEGMENT 3
#endif

static inline void bench_heap_setup(void) {
    fb_heap_init_segments(FB_HEAP_SEGMENT, FB_HEAP_SEGMENT_COUNT,
                          FB_HEAP_OFFSET, FB_RAM_BYTES);
}

static inline void bench_log(uint64_t tag, uint64_t phase, uint64_t value) {
    fb_debug_log(tag, phase, value, 0, 0);
}

static inline void bench_fill_i8(int8_t *buf, size_t len, int8_t start) {
    for (size_t i = 0; i < len; i++) {
        buf[i] = (int8_t)(start + (int8_t)i);
    }
}

static inline void bench_fill_i32(int32_t *buf, size_t len, int32_t start) {
    for (size_t i = 0; i < len; i++) {
        buf[i] = start + (int32_t)i;
    }
}

static inline void bench_fill_f32(float *buf, size_t len, float start) {
    for (size_t i = 0; i < len; i++) {
        buf[i] = start + (float)i * 0.25f;
    }
}

static inline void bench_init_graph(void) {
    if (FB_GRAPH_SEGMENT == 0) {
        return;
    }

    uint8_t *base = (uint8_t *)(uintptr_t)FB_SEGMENT_ADDR(FB_GRAPH_SEGMENT, 0);
    uint32_t *u32 = (uint32_t *)base;
    u32[0] = 0x48505247; /* GRPH */
    u32[1] = 1;          /* num_edges */
    u32[2] = 4;          /* dim */
    u32[3] = 0;          /* padding */

    uint32_t *target = (uint32_t *)(base + 16);
    *target = 7;
    int8_t *weights = (int8_t *)(base + 20);
    weights[0] = 1;
    weights[1] = 1;
    weights[2] = 1;
    weights[3] = 1;
}

static inline void bench_init_arb(void) {
    if (FB_ARB_SEGMENT == 0) {
        return;
    }

    uint8_t *base = (uint8_t *)(uintptr_t)FB_SEGMENT_ADDR(FB_ARB_SEGMENT, 0);
    fb_memset(base, 0, 64);
    base[16] = 0;
    base[17] = 0;
    base[18] = 0;
}

#endif /* FB_BENCH_COMMON_H */
