// Frostbite minimal allocator + memory helpers.
//
// Provides a simple bump allocator and byte-wise memcpy/memset for
// freestanding C programs. The allocator always uses a mapped RAM
// account segment; it never falls back to local heap memory.

#include <stddef.h>
#include <stdint.h>

#define FB_RUNTIME_IMPLEMENTATION 1
#include "frostbite.h"

#ifndef FB_HEAP_SEGMENT
#define FB_HEAP_SEGMENT 1
#endif

#ifndef FB_HEAP_OFFSET
#define FB_HEAP_OFFSET 0
#endif

#ifndef FB_RAM_BYTES
#define FB_RAM_BYTES (4u * 1024u * 1024u)
#endif

#ifndef FB_HEAP_SEGMENT_COUNT
#define FB_HEAP_SEGMENT_COUNT 1
#endif

#ifndef FB_SEGMENT_ADDR
#define FB_SEGMENT_ADDR(seg, offset) \
    ((((uint64_t)(seg)) << 28) | ((uint64_t)(offset) & 0x0FFFFFFFULL))
#endif

static uint8_t *fb_heap_ptr = NULL;
static uint8_t *fb_heap_end = NULL;
static uint32_t fb_heap_segment_start = FB_HEAP_SEGMENT;
static uint32_t fb_heap_segment_count = FB_HEAP_SEGMENT_COUNT;
static uint32_t fb_heap_segment_index = 0;
static size_t fb_heap_segment_bytes = FB_RAM_BYTES;
static size_t fb_heap_segment_offset = FB_HEAP_OFFSET;
static int fb_heap_use_segments = 1;

__attribute__((weak)) void fb_alloc_panic(const char *msg) {
    fb_print_str(msg);
    fb_exit(1);
}

static size_t fb_align_up(size_t value, size_t align) {
    return (value + align - 1u) & ~(align - 1u);
}

static int fb_is_segment_addr(uintptr_t addr) {
    return ((addr >> 28) & 0x0F) != 0;
}

static void fb_heap_set_segment(uint32_t index) {
    if (fb_heap_segment_start == 0 || fb_heap_segment_count == 0) {
        fb_alloc_panic(
            "fb_malloc: RAM heap not configured. Pass RAM accounts and set "
            "FB_HEAP_SEGMENT>0 (default=1).\n"
        );
    }
    if (index >= fb_heap_segment_count) {
        fb_heap_ptr = NULL;
        fb_heap_end = NULL;
        return;
    }
    uint32_t segment = fb_heap_segment_start + index;
    size_t offset = (index == 0) ? fb_heap_segment_offset : 0;
    if (fb_heap_segment_bytes <= offset) {
        fb_alloc_panic(
            "fb_malloc: RAM heap offset exceeds RAM size. Check FB_HEAP_OFFSET "
            "and FB_RAM_BYTES.\n"
        );
    }
    uintptr_t base = (uintptr_t)FB_SEGMENT_ADDR(segment, offset);
    fb_heap_ptr = (uint8_t *)base;
    fb_heap_end = (uint8_t *)(base + (fb_heap_segment_bytes - offset));
}

static void fb_heap_init_default(void) {
    if (fb_heap_ptr == NULL || fb_heap_end == NULL) {
        fb_heap_use_segments = 1;
        fb_heap_segment_start = FB_HEAP_SEGMENT;
        fb_heap_segment_count = FB_HEAP_SEGMENT_COUNT;
        fb_heap_segment_index = 0;
        fb_heap_segment_bytes = FB_RAM_BYTES;
        fb_heap_segment_offset = FB_HEAP_OFFSET;
        fb_heap_set_segment(0);
    }
}

void fb_heap_init(void *base, size_t size) {
    if (base != NULL && size != 0) {
        uintptr_t addr = (uintptr_t)base;
        if (!fb_is_segment_addr(addr)) {
            fb_alloc_panic(
                "fb_heap_init: base must be a RAM segment address. Use "
                "FB_SEGMENT_ADDR(seg, offset).\n"
            );
        }
        fb_heap_use_segments = 0;
        fb_heap_ptr = (uint8_t *)base;
        fb_heap_end = fb_heap_ptr + size;
    } else {
        fb_heap_use_segments = 1;
        fb_heap_ptr = NULL;
        fb_heap_end = NULL;
    }
}

void fb_heap_init_segments(uint32_t start_segment, uint32_t count,
                           size_t offset, size_t bytes_per_segment) {
    if (start_segment == 0 || count == 0 || bytes_per_segment == 0) {
        fb_alloc_panic(
            "fb_heap_init_segments: invalid RAM segment configuration.\n"
        );
    }
    fb_heap_use_segments = 1;
    fb_heap_segment_start = start_segment;
    fb_heap_segment_count = count;
    fb_heap_segment_index = 0;
    fb_heap_segment_bytes = bytes_per_segment;
    fb_heap_segment_offset = offset;
    fb_heap_set_segment(0);
}

void *fb_malloc(size_t size) {
    if (size == 0) {
        return NULL;
    }

    fb_heap_init_default();

    size = fb_align_up(size, 8u);
retry:
    uintptr_t ptr = (uintptr_t)fb_heap_ptr;
    uintptr_t end = (uintptr_t)fb_heap_end;

    if (ptr + size > end) {
        if (fb_heap_use_segments &&
            (fb_heap_segment_index + 1) < fb_heap_segment_count) {
            fb_heap_segment_index++;
            fb_heap_set_segment(fb_heap_segment_index);
            goto retry;
        }
        return NULL;
    }

    fb_heap_ptr = (uint8_t *)(ptr + size);
    return (void *)ptr;
}

void fb_free(void *ptr) {
    (void)ptr;
}

void *fb_memcpy(void *dst, const void *src, size_t n) {
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;

    for (size_t i = 0; i < n; i++) {
        d[i] = s[i];
    }

    return dst;
}

void *fb_memset(void *dst, int c, size_t n) {
    uint8_t *d = (uint8_t *)dst;
    uint8_t value = (uint8_t)c;

    for (size_t i = 0; i < n; i++) {
        d[i] = value;
    }

    return dst;
}

__attribute__((weak)) void *malloc(size_t size) {
    return fb_malloc(size);
}

__attribute__((weak)) void free(void *ptr) {
    fb_free(ptr);
}

__attribute__((weak)) void *memcpy(void *dst, const void *src, size_t n) {
    return fb_memcpy(dst, src, n);
}

__attribute__((weak)) void *memset(void *dst, int c, size_t n) {
    return fb_memset(dst, c, n);
}
