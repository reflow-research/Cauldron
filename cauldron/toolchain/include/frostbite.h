/**
 * Frostbite VM - C SDK (Syscall Wrappers)
 *
 * Provides documented wrappers for all Frostbite VM syscalls.
 * Target: RISC-V RV64IM (local CLI) / RV64IMAC (on-chain).
 */

#ifndef FROSTBITE_H
#define FROSTBITE_H

#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Syscall IDs
 * ============================================================================ */

#define FB_SYS_PUTCHAR                 60
#define FB_SYS_WRITE                   64
#define FB_SYS_EXIT                    93
#define FB_SYS_YIELD                   123

#define FB_SYS_MATMUL                  110
#define FB_SYS_RMSNORM                 111
#define FB_SYS_SOFTMAX                 112
#define FB_SYS_SILU                    113
#define FB_SYS_ROPE                    114
#define FB_SYS_MATMUL_Q8               115
#define FB_SYS_ACCUM                   116
#define FB_SYS_READ_F32                117
#define FB_SYS_WRITE_F32               118
#define FB_SYS_MEMCPY_F32              119
#define FB_SYS_MATMUL_Q8_PARTIAL       120
#define FB_SYS_ARGMAX_PARTIAL          121
#define FB_SYS_DEBUG_LOG               122

#define FB_SYS_MATMUL_I8_I32           130
#define FB_SYS_SOFTMAX_I32             131
#define FB_SYS_DOT_I32                 132
#define FB_SYS_WEIGHTED_SUM_I32        133
#define FB_SYS_MATMUL_I8_I32_PARTIAL   134
#define FB_SYS_ARGMAX_I32_PARTIAL      135
#define FB_SYS_SOFTMAX_I32_F32         136
#define FB_SYS_SILU_MUL_I32            137
#define FB_SYS_RMSNORM_I32             138
#define FB_SYS_MATMUL_I8_I8            139
#define FB_SYS_MATMUL_I8_I8_PARTIAL    140
#define FB_SYS_MATMUL_I8_I8_QKV        141
#define FB_SYS_MATMUL_I8_I8_W1W3       142
#define FB_SYS_MATMUL_I8_I8_ARGMAX     143
#define FB_SYS_MATMUL_I8_I8_W1W3_SILU  144

#define FB_SYS_DOT_I8                  7001
#define FB_SYS_VEC_ADD_I8              7003
#define FB_SYS_ACTIVATION              7010

#define FB_SYS_GRAPH_SEARCH            8001
#define FB_SYS_GRAPH_SEARCH_ALT        8002
#define FB_SYS_ARB_SEARCH              8005
#define FB_SYS_ARB_SCORE               8010
#define FB_SYS_AGGREGATE               8020

#define FB_SYS_QUANTUM_OP              9000

/* ============================================================================
 * Flags, constants, and helpers
 * ============================================================================ */

#define FB_ALIGN4(n) (((n) + 3u) & ~3u)

/* Q8 flags for MATMUL_Q8 and MATMUL_Q8_PARTIAL */
#define FB_Q8_FLAG_PREQUANT     (1ULL << 63)
#define FB_Q8_FLAG_TENSOR_SCALE (1ULL << 62)
#define FB_Q8_FLAG_MASK         (FB_Q8_FLAG_PREQUANT | FB_Q8_FLAG_TENSOR_SCALE)

/* Activation types */
#define FB_ACT_RELU    0
#define FB_ACT_SIGMOID 1

/* Virtual address helpers */
#define FB_SCRATCH_ADDR(offset) ((uint64_t)(offset))
#define FB_SEGMENT_ADDR(seg, offset) \
    ((((uint64_t)(seg)) << 28) | ((uint64_t)(offset) & 0x0FFFFFFFULL))

/* Quantum opcodes */
#define FB_QOP_INIT    0
#define FB_QOP_H       1
#define FB_QOP_CNOT    2
#define FB_QOP_MEASURE 3
#define FB_QOP_RX      4
#define FB_QOP_RZ      5
#define FB_QOP_PHASE   6

#define FB_QUANTUM_NUM_QUBITS 7
#define FB_QUANTUM_STATE_LEN (1u << FB_QUANTUM_NUM_QUBITS)

typedef struct {
    int32_t re;
    int32_t im;
} fb_q16_complex_t;

/* Common row cursor state (u32 cursor, u32 max_rows) */
typedef struct {
    uint32_t cursor;
    uint32_t max_rows;
} fb_row_state_t;

/* Yield state (u32 flag: 0 yield, 1 clear) */
typedef struct {
    uint32_t flag;
} fb_yield_state_t;

/* Argmax state (f32 bits) */
typedef struct {
    uint32_t cursor;
    uint32_t max_idx;
    uint32_t max_bits;
    uint32_t max_per_call;
} fb_argmax_state_t;

/* Argmax state (i32) */
typedef struct {
    uint32_t cursor;
    uint32_t max_idx;
    int32_t max_val;
    uint32_t max_per_call;
} fb_argmax_i32_state_t;

/* MATMUL_I8_I8_ARGMAX state word offsets */
#define FB_I8_I8_ARGMAX_CURSOR_WORD     0u
#define FB_I8_I8_ARGMAX_MAX_IDX_WORD    1u
#define FB_I8_I8_ARGMAX_MAX_VAL_WORD    2u
#define FB_I8_I8_ARGMAX_MAX_ROWS_WORD   3u
#define FB_I8_I8_ARGMAX_TOPK2_WORD      4u
#define FB_I8_I8_ARGMAX_FILLED2_WORD    5u
#define FB_I8_I8_ARGMAX_MIN_VAL2_WORD   6u
#define FB_I8_I8_ARGMAX_MIN_POS2_WORD   7u
#define FB_I8_I8_ARGMAX_SHORT_N2_WORD   8u
#define FB_I8_I8_ARGMAX_TOPK1_WORD      9u
#define FB_I8_I8_ARGMAX_FILLED1_WORD    10u
#define FB_I8_I8_ARGMAX_MIN_VAL1_WORD   11u
#define FB_I8_I8_ARGMAX_MIN_POS1_WORD   12u
#define FB_I8_I8_ARGMAX_SHORT_N1_WORD   13u
#define FB_I8_I8_ARGMAX_STAGE2_WORD     14u
#define FB_I8_I8_ARGMAX_FULL_WORD       15u
#define FB_I8_I8_ARGMAX_STAGE2_MAX_WORD 16u
#define FB_I8_I8_ARGMAX_FULL_MAX_WORD   17u
#define FB_I8_I8_ARGMAX_HEADER_WORDS    18u

/* MATMUL_I8_I8_QKV config */
typedef struct {
    uint64_t out_q;
    uint64_t out_k;
    uint64_t out_v;
    uint64_t x_ptr;
    uint64_t wq_ptr;
    uint64_t wk_ptr;
    uint64_t wv_ptr;
    uint32_t wq_scale;
    uint32_t wk_scale;
    uint32_t wv_scale;
    uint32_t n;
    uint32_t d_q;
    uint32_t d_k;
    uint32_t d_v;
    uint32_t _pad0;
    uint64_t state_ptr;
} fb_matmul_qkv_cfg_t;

/* MATMUL_I8_I8_W1W3 config */
typedef struct {
    uint64_t out_a;
    uint64_t out_b;
    uint64_t x_ptr;
    uint64_t w1_ptr;
    uint64_t w3_ptr;
    uint32_t w1_scale;
    uint32_t w3_scale;
    uint32_t n;
    uint32_t d;
    uint64_t state_ptr;
} fb_matmul_w1w3_cfg_t;

/* MATMUL_I8_I8_W1W3_SILU config */
typedef struct {
    uint64_t out_ptr;
    uint64_t x_ptr;
    uint64_t w1_ptr;
    uint64_t w3_ptr;
    uint32_t w1_scale;
    uint32_t w3_scale;
    uint32_t n;
    uint32_t d;
    uint64_t state_ptr;
} fb_matmul_w1w3_silu_cfg_t;

/* ============================================================================
 * Low-level syscall helpers
 * ============================================================================ */

static inline long fb_syscall0(long id) {
    register long a0 asm("a0") = 0;
    register long a7 asm("a7") = id;
    asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
    return a0;
}

static inline long fb_syscall1(long id, long arg0) {
    register long a0 asm("a0") = arg0;
    register long a7 asm("a7") = id;
    asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
    return a0;
}

static inline long fb_syscall2(long id, long arg0, long arg1) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a7 asm("a7") = id;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a7) : "memory");
    return a0;
}

static inline long fb_syscall3(long id, long arg0, long arg1, long arg2) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a7 asm("a7") = id;
    asm volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
    return a0;
}

static inline long fb_syscall4(long id, long arg0, long arg1, long arg2, long arg3) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a7 asm("a7") = id;
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a7)
                 : "memory");
    return a0;
}

static inline long fb_syscall5(long id, long arg0, long arg1, long arg2, long arg3, long arg4) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a4 asm("a4") = arg4;
    register long a7 asm("a7") = id;
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a7)
                 : "memory");
    return a0;
}

static inline long fb_syscall6(long id, long arg0, long arg1, long arg2, long arg3, long arg4,
                               long arg5) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a4 asm("a4") = arg4;
    register long a5 asm("a5") = arg5;
    register long a7 asm("a7") = id;
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a7)
                 : "memory");
    return a0;
}

static inline long fb_syscall7(long id, long arg0, long arg1, long arg2, long arg3, long arg4,
                               long arg5, long arg6) {
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a4 asm("a4") = arg4;
    register long a5 asm("a5") = arg5;
    register long a6 asm("a6") = arg6;
    register long a7 asm("a7") = id;
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a5), "r"(a6), "r"(a7)
                 : "memory");
    return a0;
}

/* ============================================================================
 * System syscalls
 * ============================================================================ */

/**
 * Exit the VM with the given code.
 */
static inline __attribute__((noreturn)) void fb_exit(long code) {
    fb_syscall1(FB_SYS_EXIT, code);
    __builtin_unreachable();
}

/**
 * Write bytes to the VM log.
 *
 * @param buf Pointer to bytes
 * @param len Byte length
 * @return bytes written
 */
static inline long fb_write(const void *buf, size_t len) {
    return fb_syscall3(FB_SYS_WRITE, 1, (long)buf, (long)len);
}

/**
 * Write a single character.
 */
static inline void fb_putchar(char c) {
    fb_syscall1(FB_SYS_PUTCHAR, (long)(unsigned char)c);
}

/**
 * Yield execution. state->flag toggles between 0 and 1.
 */
static inline void fb_yield(fb_yield_state_t *state) {
    fb_syscall1(FB_SYS_YIELD, (long)state);
}

/**
 * Print a null-terminated string without format parsing.
 */
static inline void fb_print_str(const char *s) {
    size_t len = 0;
    while (s[len]) {
        len++;
    }
    fb_write(s, len);
}

static inline void fb_print_uint(uint64_t value, unsigned base, int uppercase) {
    char buf[32];
    size_t i = 0;
    const char *digits = uppercase ? "0123456789ABCDEF" : "0123456789abcdef";

    if (value == 0) {
        fb_putchar('0');
        return;
    }

    while (value > 0 && i < sizeof(buf)) {
        buf[i++] = digits[value % base];
        value /= base;
    }

    while (i > 0) {
        fb_putchar(buf[--i]);
    }
}

static inline void fb_print_int(int64_t value) {
    uint64_t abs_value;

    if (value < 0) {
        fb_putchar('-');
        abs_value = (uint64_t)(-(value + 1)) + 1;
    } else {
        abs_value = (uint64_t)value;
    }

    fb_print_uint(abs_value, 10, 0);
}

static inline void fb_vprintf(const char *fmt, va_list ap) {
    const char *chunk = fmt;

    while (*fmt) {
        if (*fmt != '%') {
            fmt++;
            continue;
        }

        if (fmt > chunk) {
            fb_write(chunk, (size_t)(fmt - chunk));
        }

        fmt++;
        if (*fmt == '\0') {
            fb_putchar('%');
            return;
        }
        if (*fmt == '%') {
            fb_putchar('%');
            fmt++;
            chunk = fmt;
            continue;
        }

        int length = 0;
        if (*fmt == 'l') {
            length = 1;
            fmt++;
            if (*fmt == 'l') {
                length = 2;
                fmt++;
            }
        } else if (*fmt == 'z') {
            length = 1;
            fmt++;
        }

        if (*fmt == '\0') {
            fb_putchar('%');
            return;
        }

        switch (*fmt) {
            case 'd':
            case 'i': {
                int64_t v;
                if (length == 2) {
                    v = (int64_t)va_arg(ap, long long);
                } else if (length == 1) {
                    v = (int64_t)va_arg(ap, long);
                } else {
                    v = (int64_t)va_arg(ap, int);
                }
                fb_print_int(v);
                break;
            }
            case 'u': {
                uint64_t v;
                if (length == 2) {
                    v = (uint64_t)va_arg(ap, unsigned long long);
                } else if (length == 1) {
                    v = (uint64_t)va_arg(ap, unsigned long);
                } else {
                    v = (uint64_t)va_arg(ap, unsigned int);
                }
                fb_print_uint(v, 10, 0);
                break;
            }
            case 'x':
            case 'X': {
                int uppercase = (*fmt == 'X');
                uint64_t v;
                if (length == 2) {
                    v = (uint64_t)va_arg(ap, unsigned long long);
                } else if (length == 1) {
                    v = (uint64_t)va_arg(ap, unsigned long);
                } else {
                    v = (uint64_t)va_arg(ap, unsigned int);
                }
                fb_print_uint(v, 16, uppercase);
                break;
            }
            case 'p': {
                uintptr_t v = (uintptr_t)va_arg(ap, void *);
                fb_print_str("0x");
                fb_print_uint((uint64_t)v, 16, 0);
                break;
            }
            case 'c': {
                int v = va_arg(ap, int);
                fb_putchar((char)v);
                break;
            }
            case 's': {
                const char *s = va_arg(ap, const char *);
                if (s) {
                    fb_print_str(s);
                } else {
                    fb_print_str("(null)");
                }
                break;
            }
            default:
                fb_putchar('%');
                fb_putchar(*fmt);
                break;
        }

        fmt++;
        chunk = fmt;
    }

    if (fmt > chunk) {
        fb_write(chunk, (size_t)(fmt - chunk));
    }
}

/**
 * Print a format string (printf-style).
 *
 * Supported: %d %i %u %x %X %p %s %c %%
 * Length: l, ll, z
 */
static inline void fb_printf(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fb_vprintf(fmt, ap);
    va_end(ap);
}

/* fb_print("str") -> fb_print_str, fb_print("x=%d", x) -> fb_printf */
#define FB_PRINT_DISPATCH(_1,_2,_3,_4,_5,_6,_7,_8,_9,_10,_11,_12,_13,_14,_15,_16,NAME,...) NAME
#define fb_print(...) \
    FB_PRINT_DISPATCH(__VA_ARGS__, \
        fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, \
        fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_printf, fb_print_str) \
    (__VA_ARGS__)

/* ============================================================================
 * Heap + memory utilities
 * ============================================================================ */

/**
 * Initialize heap bounds for fb_malloc (base/size). The heap must always be a
 * mapped RAM segment address (use FB_SEGMENT_ADDR). No local heap fallback.
 *
 * To default to a mapped RAM segment without calling fb_heap_init, compile with:
 * -DFB_HEAP_SEGMENT=<seg> [-DFB_HEAP_SEGMENT_COUNT=<n>]
 * [-DFB_HEAP_OFFSET=<bytes>] [-DFB_RAM_BYTES=<bytes>].
 * The default heap segment is 1; multi-segment heaps consume contiguous segments.
 *
 * fb_malloc always allocates from a RAM segment. If no RAM accounts are mapped
 * (or FB_HEAP_SEGMENT is 0), fb_malloc exits with a descriptive error.
 */
void fb_heap_init(void *base, size_t size);

/**
 * Initialize heap using multiple mapped segments.
 *
 * @param start_segment First RAM segment number (>=1)
 * @param count         Number of contiguous RAM segments
 * @param offset        Offset applied only to the first segment
 * @param bytes_per_seg Size of each RAM segment in bytes
 */
void fb_heap_init_segments(uint32_t start_segment, uint32_t count,
                           size_t offset, size_t bytes_per_seg);

/**
 * Initialize heap using a mapped segment base (offset 0).
 */
static inline void fb_heap_init_segment(uint32_t segment, size_t size) {
    fb_heap_init_segments(segment, 1, 0, size);
}

/**
 * Simple bump allocator (returns NULL on OOM).
 */
void *fb_malloc(size_t size);

/**
 * Free is a no-op for the bump allocator.
 */
void fb_free(void *ptr);

/* Optional libc-style aliases (weakly defined in the runtime). */
void *malloc(size_t size);
void free(void *ptr);
void *memcpy(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);

/* ============================================================================
 * LLM syscalls (110-144)
 * ============================================================================ */

/**
 * MATMUL (deprecated): out = W @ x (f32).
 */
static inline long fb_matmul(float *out, const float *x, const float *w,
                             size_t n, size_t d) {
    return fb_syscall5(FB_SYS_MATMUL, (long)out, (long)x, (long)w,
                       (long)n, (long)d);
}

/**
 * RMSNORM: out = (x / rms) * weight.
 */
static inline void fb_rmsnorm(float *out, const float *x, const float *weight,
                              size_t size) {
    fb_syscall4(FB_SYS_RMSNORM, (long)out, (long)x, (long)weight, (long)size);
}

/**
 * SOFTMAX: in-place softmax on f32.
 */
static inline void fb_softmax(float *data, size_t size) {
    fb_syscall2(FB_SYS_SOFTMAX, (long)data, (long)size);
}

/**
 * SILU: in-place SiLU on f32.
 */
static inline void fb_silu(float *data, size_t size) {
    fb_syscall2(FB_SYS_SILU, (long)data, (long)size);
}

/**
 * ROPE: rotary embeddings on q/k vectors.
 */
static inline void fb_rope(float *q, float *k, int pos, int dim, int head_size) {
    fb_syscall5(FB_SYS_ROPE, (long)q, (long)k, (long)pos, (long)dim, (long)head_size);
}

/**
 * MATMUL_Q8: Quantized int8 matmul.
 *
 * @param out       f32 output
 * @param x         f32 input or prequant buffer
 * @param w         int8 weights
 * @param scale     per-row f32 scales or tensor scale
 * @param n_flags   n with FB_Q8_FLAG_* bits
 * @param d         output rows
 */
static inline void fb_matmul_q8(float *out, const void *x, const int8_t *w,
                                const void *scale, uint64_t n_flags, size_t d) {
    fb_syscall6(FB_SYS_MATMUL_Q8, (long)out, (long)x, (long)w,
                (long)scale, (long)n_flags, (long)d);
}

/**
 * MATMUL_Q8_PARTIAL: resumable rows.
 */
static inline void fb_matmul_q8_partial(float *out, const void *x, const int8_t *w,
                                        const void *scale, uint64_t n_flags, size_t d,
                                        fb_row_state_t *state) {
    fb_syscall7(FB_SYS_MATMUL_Q8_PARTIAL, (long)out, (long)x, (long)w,
                (long)scale, (long)n_flags, (long)d, (long)state);
}

/**
 * ACCUM: out += x (f32).
 */
static inline void fb_accum(float *out, const float *x, size_t size) {
    fb_syscall3(FB_SYS_ACCUM, (long)out, (long)x, (long)size);
}

/**
 * READ_F32: read a float from any VM address.
 */
static inline float fb_read_f32(uint64_t addr) {
    uint32_t bits = (uint32_t)fb_syscall1(FB_SYS_READ_F32, (long)addr);
    union {
        uint32_t u;
        float f;
    } v;
    v.u = bits;
    return v.f;
}

/**
 * WRITE_F32: write a float to any VM address.
 */
static inline void fb_write_f32(uint64_t addr, float val) {
    union {
        uint32_t u;
        float f;
    } v;
    v.f = val;
    fb_syscall2(FB_SYS_WRITE_F32, (long)addr, (long)v.u);
}

/**
 * MEMCPY_F32: copy f32 array between VM addresses.
 */
static inline void fb_memcpy_f32(uint64_t dst, uint64_t src, size_t count) {
    fb_syscall3(FB_SYS_MEMCPY_F32, (long)dst, (long)src, (long)count);
}

/**
 * ARGMAX_PARTIAL: resumable argmax over f32.
 *
 * @return max index when complete
 */
static inline uint32_t fb_argmax_partial(const float *data, size_t count,
                                         fb_argmax_state_t *state) {
    return (uint32_t)fb_syscall3(FB_SYS_ARGMAX_PARTIAL, (long)data, (long)count, (long)state);
}

/**
 * DEBUG_LOG: emit a tagged debug log.
 */
static inline void fb_debug_log(uint64_t tag, uint64_t a, uint64_t b,
                                uint64_t c, uint64_t d) {
    fb_syscall5(FB_SYS_DEBUG_LOG, (long)tag, (long)a, (long)b, (long)c, (long)d);
}

/**
 * MATMUL_I8_I32: int8 weights, i32 activations.
 */
static inline void fb_matmul_i8_i32(int32_t *out, const int32_t *x, const int8_t *w,
                                    int32_t scale_q16, size_t n, size_t d) {
    fb_syscall6(FB_SYS_MATMUL_I8_I32, (long)out, (long)x, (long)w,
                (long)scale_q16, (long)n, (long)d);
}

/**
 * MATMUL_I8_I32_PARTIAL: resumable rows.
 */
static inline void fb_matmul_i8_i32_partial(int32_t *out, const int32_t *x, const int8_t *w,
                                            int32_t scale_q16, size_t n, size_t d,
                                            fb_row_state_t *state) {
    fb_syscall7(FB_SYS_MATMUL_I8_I32_PARTIAL, (long)out, (long)x, (long)w,
                (long)scale_q16, (long)n, (long)d, (long)state);
}

/**
 * SOFTMAX_I32: Q16 softmax on i32.
 */
static inline void fb_softmax_i32(int32_t *data, size_t len) {
    fb_syscall2(FB_SYS_SOFTMAX_I32, (long)data, (long)len);
}

/**
 * DOT_I32: dot(a, b) >> shift.
 *
 * @return result
 */
static inline int64_t fb_dot_i32(const int32_t *a, const int32_t *b, size_t len, uint32_t shift) {
    return (int64_t)fb_syscall4(FB_SYS_DOT_I32, (long)a, (long)b, (long)len, (long)shift);
}

/**
 * WEIGHTED_SUM_I32: out[i] += (weight * src[i]) >> shift.
 */
static inline void fb_weighted_sum_i32(int32_t *out, const int32_t *src, int32_t weight,
                                       size_t len, uint32_t shift) {
    fb_syscall5(FB_SYS_WEIGHTED_SUM_I32, (long)out, (long)src, (long)weight,
                (long)len, (long)shift);
}

/**
 * ARGMAX_I32_PARTIAL: resumable argmax over i32.
 *
 * @return max index when complete
 */
static inline uint32_t fb_argmax_i32_partial(const int32_t *data, size_t count,
                                             fb_argmax_i32_state_t *state) {
    return (uint32_t)fb_syscall3(FB_SYS_ARGMAX_I32_PARTIAL, (long)data, (long)count, (long)state);
}

/**
 * SOFTMAX_I32_F32: i32 softmax using f32 math.
 */
static inline void fb_softmax_i32_f32(int32_t *data, size_t len) {
    fb_syscall2(FB_SYS_SOFTMAX_I32_F32, (long)data, (long)len);
}

/**
 * SILU_MUL_I32: gate SiLU multiply (Q16).
 */
static inline void fb_silu_mul_i32(int32_t *hb, const int32_t *hb2, size_t size) {
    fb_syscall3(FB_SYS_SILU_MUL_I32, (long)hb, (long)hb2, (long)size);
}

/**
 * RMSNORM_I32: RMSNorm for Q16 i32.
 */
static inline void fb_rmsnorm_i32(int32_t *out, const int32_t *x, uint64_t weight_addr,
                                  size_t dim) {
    fb_syscall4(FB_SYS_RMSNORM_I32, (long)out, (long)x, (long)weight_addr, (long)dim);
}

/**
 * MATMUL_I8_I8: int8 weights and prequant buffer.
 */
static inline void fb_matmul_i8_i8(int32_t *out, const void *x_prequant, const int8_t *w,
                                   int32_t w_scale_q16, size_t n, size_t d) {
    fb_syscall6(FB_SYS_MATMUL_I8_I8, (long)out, (long)x_prequant, (long)w,
                (long)w_scale_q16, (long)n, (long)d);
}

/**
 * MATMUL_I8_I8_PARTIAL: resumable rows.
 */
static inline void fb_matmul_i8_i8_partial(int32_t *out, const void *x_prequant, const int8_t *w,
                                           int32_t w_scale_q16, size_t n, size_t d,
                                           fb_row_state_t *state) {
    fb_syscall7(FB_SYS_MATMUL_I8_I8_PARTIAL, (long)out, (long)x_prequant, (long)w,
                (long)w_scale_q16, (long)n, (long)d, (long)state);
}

/**
 * MATMUL_I8_I8_ARGMAX_PARTIAL: resumable argmax over logits.
 *
 * @return max index when complete
 */
static inline uint32_t fb_matmul_i8_i8_argmax_partial(const void *x_prequant, const int8_t *w,
                                                      int32_t w_scale_q16, size_t n, size_t d,
                                                      uint32_t *state_words) {
    return (uint32_t)fb_syscall6(FB_SYS_MATMUL_I8_I8_ARGMAX, (long)x_prequant, (long)w,
                                 (long)w_scale_q16, (long)n, (long)d, (long)state_words);
}

/**
 * MATMUL_I8_I8_QKV: fused Q/K/V matmul.
 */
static inline void fb_matmul_i8_i8_qkv(const fb_matmul_qkv_cfg_t *cfg) {
    fb_syscall1(FB_SYS_MATMUL_I8_I8_QKV, (long)cfg);
}

/**
 * MATMUL_I8_I8_W1W3: fused W1/W3 matmul.
 */
static inline void fb_matmul_i8_i8_w1w3(const fb_matmul_w1w3_cfg_t *cfg) {
    fb_syscall1(FB_SYS_MATMUL_I8_I8_W1W3, (long)cfg);
}

/**
 * MATMUL_I8_I8_W1W3_SILU: fused W1/W3 matmul + SiLU.
 */
static inline void fb_matmul_i8_i8_w1w3_silu(const fb_matmul_w1w3_silu_cfg_t *cfg) {
    fb_syscall1(FB_SYS_MATMUL_I8_I8_W1W3_SILU, (long)cfg);
}

/* ============================================================================
 * AI/ML accelerator syscalls (7000-7019)
 * ============================================================================ */

/**
 * DOT_I8: dot product of int8 vectors.
 *
 * @return sum as int32
 */
static inline int32_t fb_dot_i8(const int8_t *a, const int8_t *b, size_t len) {
    return (int32_t)fb_syscall3(FB_SYS_DOT_I8, (long)a, (long)b, (long)len);
}

/**
 * VEC_ADD_I8: dst[i] += src[i].
 */
static inline void fb_vec_add_i8(int8_t *dst, const int8_t *src, size_t len) {
    fb_syscall3(FB_SYS_VEC_ADD_I8, (long)dst, (long)src, (long)len);
}

/**
 * ACTIVATION: apply activation in-place.
 */
static inline void fb_activation(int8_t *data, size_t len, int type) {
    fb_syscall3(FB_SYS_ACTIVATION, (long)data, (long)len, (long)type);
}

/* ============================================================================
 * Fused kernel syscalls (8000+)
 * ============================================================================ */

/**
 * GRAPH_SEARCH (8001/8002): graph edge search.
 *
 * @return number of hits
 */
static inline uint32_t fb_graph_search(const int8_t *input, uint64_t graph_idx,
                                       void *output, int32_t min_score, int alt) {
    long id = alt ? FB_SYS_GRAPH_SEARCH_ALT : FB_SYS_GRAPH_SEARCH;
    return (uint32_t)fb_syscall4(id, (long)input, (long)graph_idx,
                                 (long)output, (long)min_score);
}

/**
 * ARB_SEARCH: arbitrage search in graph.
 *
 * @return number of matches
 */
static inline uint32_t fb_arb_search(const void *input_mint, uint64_t graph_idx,
                                     void *output, uint64_t min_amount,
                                     const void *mask_ptr) {
    return (uint32_t)fb_syscall5(FB_SYS_ARB_SEARCH, (long)input_mint, (long)graph_idx,
                                 (long)output, (long)min_amount, (long)mask_ptr);
}

/**
 * ARB_SCORE: score edges and write mask.
 *
 * @return number of passing edges
 */
static inline uint32_t fb_arb_score(uint64_t graph_idx, const void *weights,
                                    uint64_t threshold, void *mask_ptr) {
    return (uint32_t)fb_syscall4(FB_SYS_ARB_SCORE, (long)graph_idx, (long)weights,
                                 (long)threshold, (long)mask_ptr);
}

/**
 * AGGREGATE: GNN message passing.
 *
 * @return number of unique nodes
 */
static inline uint32_t fb_aggregate(uint64_t graph_idx, void *table_ptr,
                                    void *features_ptr, uint64_t max_nodes) {
    return (uint32_t)fb_syscall4(FB_SYS_AGGREGATE, (long)graph_idx, (long)table_ptr,
                                 (long)features_ptr, (long)max_nodes);
}

/* ============================================================================
 * Quantum syscall (9000)
 * ============================================================================ */

/**
 * QUANTUM_OP: 7-qubit state ops (Q16.16 complex).
 *
 * @return measurement result for MEASURE, else 0
 */
static inline int fb_quantum_op(int op, int target, int control, void *state_ptr) {
    return (int)fb_syscall4(FB_SYS_QUANTUM_OP, (long)op, (long)target,
                            (long)control, (long)state_ptr);
}

/* ============================================================================
 * Utility functions
 * ============================================================================ */

/**
 * strlen for VM programs.
 */
static inline size_t fb_strlen(const char *s) {
    size_t len = 0;
    while (s[len]) {
        len++;
    }
    return len;
}

#ifndef FB_RUNTIME_IMPLEMENTATION
/**
 * memset for VM programs.
 */
static inline void *fb_memset(void *s, int c, size_t n) {
    unsigned char *p = (unsigned char *)s;
    while (n--) {
        *p++ = (unsigned char)c;
    }
    return s;
}

/**
 * memcpy for VM programs.
 */
static inline void *fb_memcpy(void *dest, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dest;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) {
        *d++ = *s++;
    }
    return dest;
}
#endif

#ifdef __cplusplus
}
#endif

#endif /* FROSTBITE_H */
