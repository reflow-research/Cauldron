/**
 * Soft-float implementation for RV64IM bare-metal.
 * Provides float and double compiler builtins.
 */

typedef unsigned int u32;
typedef int i32;
typedef unsigned long long u64;
typedef long long i64;

#define FB_WEAK __attribute__((weak))

/* ---- float (f32) ---- */

static inline u32 f32_to_bits(float f) {
    union { float f; u32 u; } x;
    x.f = f;
    return x.u;
}

static inline float bits_to_f32(u32 u) {
    union { u32 u; float f; } x;
    x.u = u;
    return x.f;
}

static inline int f32_sign(u32 a) { return (a >> 31) & 1; }
static inline int f32_exp(u32 a) { return (a >> 23) & 0xFF; }
static inline u32 f32_frac(u32 a) { return a & 0x7FFFFF; }
static inline int f32_is_nan(u32 a) { return (f32_exp(a) == 0xFF && f32_frac(a)); }

static int f32_cmp(float a, float b, int *unordered) {
    u32 ua = f32_to_bits(a);
    u32 ub = f32_to_bits(b);
    if (f32_is_nan(ua) || f32_is_nan(ub)) {
        if (unordered) *unordered = 1;
        return 0;
    }
    if ((ua & 0x7FFFFFFF) == 0 && (ub & 0x7FFFFFFF) == 0) return 0;
    i32 sa = (i32)ua;
    i32 sb = (i32)ub;
    if (sa < 0) sa = 0x80000000 - sa;
    if (sb < 0) sb = 0x80000000 - sb;
    if (sa < sb) return -1;
    if (sa > sb) return 1;
    return 0;
}

FB_WEAK int __gtsf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    return unordered ? -1 : cmp;
}
FB_WEAK int __gesf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    return unordered ? -1 : cmp;
}
FB_WEAK int __ltsf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    return unordered ? 1 : cmp;
}
FB_WEAK int __lesf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    return unordered ? 1 : cmp;
}
FB_WEAK int __eqsf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    if (unordered) return 1;
    return (cmp == 0) ? 0 : 1;
}
FB_WEAK int __nesf2(float a, float b) {
    int unordered = 0;
    int cmp = f32_cmp(a, b, &unordered);
    if (unordered) return 1;
    return (cmp == 0) ? 0 : 1;
}
FB_WEAK int __unordsf2(float a, float b) {
    u32 ua = f32_to_bits(a);
    u32 ub = f32_to_bits(b);
    return ((f32_exp(ua) == 0xFF && f32_frac(ua)) ||
            (f32_exp(ub) == 0xFF && f32_frac(ub))) ? 1 : 0;
}

FB_WEAK float __addsf3(float a, float b) {
    u32 ua = f32_to_bits(a);
    u32 ub = f32_to_bits(b);
    if ((ua & 0x7FFFFFFF) == 0) return b;
    if ((ub & 0x7FFFFFFF) == 0) return a;
    int sa = f32_sign(ua), sb = f32_sign(ub);
    int ea = f32_exp(ua), eb = f32_exp(ub);
    u32 fa = f32_frac(ua) | 0x800000;
    u32 fb = f32_frac(ub) | 0x800000;
    if (ea == 0) return b;
    if (eb == 0) return a;
    int diff = ea - eb;
    if (diff > 0) {
        if (diff > 24) return a;
        fb >>= diff;
        eb = ea;
    } else if (diff < 0) {
        diff = -diff;
        if (diff > 24) return b;
        fa >>= diff;
        ea = eb;
    }
    u64 fr;
    int sr;
    if (sa == sb) {
        fr = (u64)fa + fb;
        sr = sa;
    } else {
        if (fa >= fb) {
            fr = fa - fb;
            sr = sa;
        } else {
            fr = fb - fa;
            sr = sb;
        }
    }
    if (fr == 0) return bits_to_f32(0);
    int er = ea;
    while (fr >= 0x1000000) { fr >>= 1; er++; }
    while (fr < 0x800000 && er > 0) { fr <<= 1; er--; }
    if (er >= 255) return bits_to_f32(sr ? 0xFF800000 : 0x7F800000);
    if (er <= 0) return bits_to_f32((u32)sr << 31);
    return bits_to_f32(((u32)sr << 31) | ((u32)er << 23) | ((u32)fr & 0x7FFFFF));
}

FB_WEAK float __subsf3(float a, float b) {
    u32 ub = f32_to_bits(b);
    return __addsf3(a, bits_to_f32(ub ^ 0x80000000));
}

FB_WEAK float __mulsf3(float a, float b) {
    u32 ua = f32_to_bits(a);
    u32 ub = f32_to_bits(b);
    int sa = f32_sign(ua), sb = f32_sign(ub);
    int ea = f32_exp(ua), eb = f32_exp(ub);
    u32 fa = f32_frac(ua), fb = f32_frac(ub);
    int sr = sa ^ sb;
    if ((ua & 0x7FFFFFFF) == 0 || (ub & 0x7FFFFFFF) == 0)
        return bits_to_f32((u32)sr << 31);
    if (ea == 255 || eb == 255)
        return bits_to_f32(((u32)sr << 31) | 0x7F800000);
    fa |= 0x800000;
    fb |= 0x800000;
    u64 fr = (u64)fa * fb;
    int er = ea + eb - 127;
    fr >>= 23;
    if (fr >= 0x1000000) { fr >>= 1; er++; }
    if (er >= 255) return bits_to_f32(((u32)sr << 31) | 0x7F800000);
    if (er <= 0) return bits_to_f32((u32)sr << 31);
    return bits_to_f32(((u32)sr << 31) | ((u32)er << 23) | ((u32)fr & 0x7FFFFF));
}

FB_WEAK float __divsf3(float a, float b) {
    u32 ua = f32_to_bits(a);
    u32 ub = f32_to_bits(b);
    int sa = f32_sign(ua), sb = f32_sign(ub);
    int ea = f32_exp(ua), eb = f32_exp(ub);
    u32 fa = f32_frac(ua), fb = f32_frac(ub);
    int sr = sa ^ sb;
    if ((ub & 0x7FFFFFFF) == 0)
        return bits_to_f32(((u32)sr << 31) | 0x7F800000);
    if ((ua & 0x7FFFFFFF) == 0)
        return bits_to_f32((u32)sr << 31);
    fa |= 0x800000;
    fb |= 0x800000;
    u64 fr = ((u64)fa << 24) / fb;
    int er = ea - eb + 127;
    while (fr >= 0x1000000) { fr >>= 1; er++; }
    while (fr < 0x800000 && er > 0) { fr <<= 1; er--; }
    if (er >= 255) return bits_to_f32(((u32)sr << 31) | 0x7F800000);
    if (er <= 0) return bits_to_f32((u32)sr << 31);
    return bits_to_f32(((u32)sr << 31) | ((u32)er << 23) | ((u32)fr & 0x7FFFFF));
}

FB_WEAK int __fixsfsi(float a) {
    u32 ua = f32_to_bits(a);
    int s = f32_sign(ua);
    int e = f32_exp(ua);
    u32 f = f32_frac(ua) | 0x800000;
    if (e < 127) return 0;
    if (e >= 127 + 31) return s ? (-2147483647 - 1) : 2147483647;
    int shift = e - 127 - 23;
    int result = (shift >= 0) ? (int)(f << shift) : (int)(f >> (-shift));
    return s ? -result : result;
}

FB_WEAK float __floatsisf(int a) {
    if (a == 0) return bits_to_f32(0);
    int s = 0;
    u32 ua;
    if (a < 0) { s = 1; ua = (u32)(-(long long)a); }
    else { ua = (u32)a; }
    int e = 127 + 31;
    while ((ua & 0x80000000) == 0) { ua <<= 1; e--; }
    return bits_to_f32(((u32)s << 31) | ((u32)e << 23) | ((ua >> 8) & 0x7FFFFF));
}

FB_WEAK float __floatunsisf(unsigned int a) {
    if (a == 0) return bits_to_f32(0);
    int e = 127 + 31;
    u32 ua = a;
    while ((ua & 0x80000000) == 0) { ua <<= 1; e--; }
    return bits_to_f32(((u32)e << 23) | ((ua >> 8) & 0x7FFFFF));
}

FB_WEAK unsigned int __fixunssfsi(float a) {
    u32 ua = f32_to_bits(a);
    if (f32_sign(ua)) return 0;
    int e = f32_exp(ua);
    u32 f = f32_frac(ua) | 0x800000;
    if (e < 127) return 0;
    if (e >= 127 + 32) return 0xFFFFFFFF;
    int shift = e - 127 - 23;
    return (shift >= 0) ? (f << shift) : (f >> (-shift));
}

FB_WEAK float __negsf2(float a) {
    return bits_to_f32(f32_to_bits(a) ^ 0x80000000);
}

/* ---- double (f64) ---- */

static inline u64 f64_to_bits(double f) {
    union { double f; u64 u; } x;
    x.f = f;
    return x.u;
}

static inline double bits_to_f64(u64 u) {
    union { u64 u; double f; } x;
    x.u = u;
    return x.f;
}

static inline int f64_sign(u64 a) { return (int)((a >> 63) & 1); }
static inline int f64_exp(u64 a) { return (int)((a >> 52) & 0x7FF); }
static inline u64 f64_frac(u64 a) { return a & 0xFFFFFFFFFFFFFULL; }
static inline int f64_is_nan(u64 a) { return (f64_exp(a) == 0x7FF && f64_frac(a)); }

static int f64_cmp(double a, double b, int *unordered) {
    u64 ua = f64_to_bits(a);
    u64 ub = f64_to_bits(b);
    if (f64_is_nan(ua) || f64_is_nan(ub)) {
        if (unordered) *unordered = 1;
        return 0;
    }
    if ((ua & 0x7FFFFFFFFFFFFFFFULL) == 0 &&
        (ub & 0x7FFFFFFFFFFFFFFFULL) == 0) return 0;
    int sa = f64_sign(ua);
    int sb = f64_sign(ub);
    if (sa != sb) return sa ? -1 : 1;
    u64 ma = ua & 0x7FFFFFFFFFFFFFFFULL;
    u64 mb = ub & 0x7FFFFFFFFFFFFFFFULL;
    if (ma == mb) return 0;
    if (sa == 0) return (ma < mb) ? -1 : 1;
    return (ma < mb) ? 1 : -1;
}

FB_WEAK int __gtdf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    return unordered ? -1 : cmp;
}
FB_WEAK int __gedf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    return unordered ? -1 : cmp;
}
FB_WEAK int __ltdf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    return unordered ? 1 : cmp;
}
FB_WEAK int __ledf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    return unordered ? 1 : cmp;
}
FB_WEAK int __eqdf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    if (unordered) return 1;
    return (cmp == 0) ? 0 : 1;
}
FB_WEAK int __nedf2(double a, double b) {
    int unordered = 0;
    int cmp = f64_cmp(a, b, &unordered);
    if (unordered) return 1;
    return (cmp == 0) ? 0 : 1;
}
FB_WEAK int __unorddf2(double a, double b) {
    u64 ua = f64_to_bits(a);
    u64 ub = f64_to_bits(b);
    return ((f64_exp(ua) == 0x7FF && f64_frac(ua)) ||
            (f64_exp(ub) == 0x7FF && f64_frac(ub))) ? 1 : 0;
}

static void mul_u64(u64 a, u64 b, u64 *hi, u64 *lo) {
    u64 a_lo = a & 0xFFFFFFFFULL;
    u64 a_hi = a >> 32;
    u64 b_lo = b & 0xFFFFFFFFULL;
    u64 b_hi = b >> 32;

    u64 p0 = a_lo * b_lo;
    u64 p1 = a_lo * b_hi;
    u64 p2 = a_hi * b_lo;
    u64 p3 = a_hi * b_hi;

    u64 mid = (p1 & 0xFFFFFFFFULL) + (p2 & 0xFFFFFFFFULL) + (p0 >> 32);
    *hi = p3 + (p1 >> 32) + (p2 >> 32) + (mid >> 32);
    *lo = (mid << 32) | (p0 & 0xFFFFFFFFULL);
}

static u64 div_u128_u64(u64 hi, u64 lo, u64 d) {
    u64 q = 0;
    u64 r = 0;
    for (int i = 0; i < 128; i++) {
        r = (r << 1) | (hi >> 63);
        hi = (hi << 1) | (lo >> 63);
        lo <<= 1;
        q <<= 1;
        if (r >= d) {
            r -= d;
            q |= 1;
        }
    }
    return q;
}

static u64 u64_to_f64_bits(u64 a, int sign) {
    if (a == 0) return (u64)sign << 63;
    int e = 1023 + 63;
    while ((a & (1ULL << 63)) == 0) { a <<= 1; e--; }
    u64 frac = (a >> 11) & 0xFFFFFFFFFFFFFULL;
    return ((u64)sign << 63) | ((u64)e << 52) | frac;
}

FB_WEAK double __adddf3(double a, double b) {
    u64 ua = f64_to_bits(a);
    u64 ub = f64_to_bits(b);
    if ((ua & 0x7FFFFFFFFFFFFFFFULL) == 0) return b;
    if ((ub & 0x7FFFFFFFFFFFFFFFULL) == 0) return a;
    int sa = f64_sign(ua), sb = f64_sign(ub);
    int ea = f64_exp(ua), eb = f64_exp(ub);
    u64 fa = f64_frac(ua);
    u64 fb = f64_frac(ub);
    if (ea == 0) return b;
    if (eb == 0) return a;
    if (ea == 0x7FF) return a;
    if (eb == 0x7FF) return b;
    fa |= (1ULL << 52);
    fb |= (1ULL << 52);
    int diff = ea - eb;
    if (diff > 0) {
        if (diff > 60) return a;
        fb >>= diff;
        eb = ea;
    } else if (diff < 0) {
        diff = -diff;
        if (diff > 60) return b;
        fa >>= diff;
        ea = eb;
    }
    u64 fr;
    int sr;
    if (sa == sb) {
        fr = fa + fb;
        sr = sa;
    } else {
        if (fa >= fb) {
            fr = fa - fb;
            sr = sa;
        } else {
            fr = fb - fa;
            sr = sb;
        }
    }
    if (fr == 0) return bits_to_f64(0);
    int er = ea;
    while (fr >= (1ULL << 53)) { fr >>= 1; er++; }
    while (fr < (1ULL << 52) && er > 0) { fr <<= 1; er--; }
    if (er >= 0x7FF) return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    if (er <= 0) return bits_to_f64((u64)sr << 63);
    return bits_to_f64(((u64)sr << 63) | ((u64)er << 52) |
                       (fr & 0xFFFFFFFFFFFFFULL));
}

FB_WEAK double __subdf3(double a, double b) {
    u64 ub = f64_to_bits(b);
    return __adddf3(a, bits_to_f64(ub ^ (1ULL << 63)));
}

FB_WEAK double __muldf3(double a, double b) {
    u64 ua = f64_to_bits(a);
    u64 ub = f64_to_bits(b);
    int sa = f64_sign(ua), sb = f64_sign(ub);
    int ea = f64_exp(ua), eb = f64_exp(ub);
    u64 fa = f64_frac(ua), fb = f64_frac(ub);
    int sr = sa ^ sb;
    if ((ua & 0x7FFFFFFFFFFFFFFFULL) == 0 ||
        (ub & 0x7FFFFFFFFFFFFFFFULL) == 0) {
        return bits_to_f64((u64)sr << 63);
    }
    if (ea == 0x7FF || eb == 0x7FF) {
        return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    }
    fa |= (1ULL << 52);
    fb |= (1ULL << 52);
    u64 hi, lo;
    mul_u64(fa, fb, &hi, &lo);
    int er = ea + eb - 1023;
    u64 fr = (hi << 12) | (lo >> 52);
    if (fr >= (1ULL << 53)) { fr >>= 1; er++; }
    if (er >= 0x7FF) return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    if (er <= 0) return bits_to_f64((u64)sr << 63);
    return bits_to_f64(((u64)sr << 63) | ((u64)er << 52) |
                       (fr & 0xFFFFFFFFFFFFFULL));
}

FB_WEAK double __divdf3(double a, double b) {
    u64 ua = f64_to_bits(a);
    u64 ub = f64_to_bits(b);
    int sa = f64_sign(ua), sb = f64_sign(ub);
    int ea = f64_exp(ua), eb = f64_exp(ub);
    u64 fa = f64_frac(ua), fb = f64_frac(ub);
    int sr = sa ^ sb;
    if ((ub & 0x7FFFFFFFFFFFFFFFULL) == 0) {
        return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    }
    if ((ua & 0x7FFFFFFFFFFFFFFFULL) == 0) {
        return bits_to_f64((u64)sr << 63);
    }
    if (ea == 0x7FF || eb == 0x7FF) {
        return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    }
    fa |= (1ULL << 52);
    fb |= (1ULL << 52);
    int er = ea - eb + 1023;
    u64 num_hi = fa >> 11;
    u64 num_lo = fa << 53;
    u64 fr = div_u128_u64(num_hi, num_lo, fb);
    while (fr >= (1ULL << 53)) { fr >>= 1; er++; }
    while (fr < (1ULL << 52) && er > 0) { fr <<= 1; er--; }
    if (er >= 0x7FF) return bits_to_f64(((u64)sr << 63) | (0x7FFULL << 52));
    if (er <= 0) return bits_to_f64((u64)sr << 63);
    return bits_to_f64(((u64)sr << 63) | ((u64)er << 52) |
                       (fr & 0xFFFFFFFFFFFFFULL));
}

FB_WEAK double __negdf2(double a) {
    return bits_to_f64(f64_to_bits(a) ^ (1ULL << 63));
}

FB_WEAK double __floatsidf(int a) {
    int sign = 0;
    u64 ua = (u64)(unsigned int)a;
    if (a < 0) {
        sign = 1;
        ua = (~ua) + 1;
    }
    return bits_to_f64(u64_to_f64_bits(ua, sign));
}

FB_WEAK double __floatunsidf(unsigned int a) {
    return bits_to_f64(u64_to_f64_bits((u64)a, 0));
}

FB_WEAK double __floatdidf(long long a) {
    int sign = 0;
    u64 ua = (u64)a;
    if (a < 0) {
        sign = 1;
        ua = (~ua) + 1;
    }
    return bits_to_f64(u64_to_f64_bits(ua, sign));
}

FB_WEAK double __floatundidf(unsigned long long a) {
    return bits_to_f64(u64_to_f64_bits((u64)a, 0));
}

FB_WEAK int __fixdfsi(double a) {
    u64 ua = f64_to_bits(a);
    int sign = f64_sign(ua);
    int exp = f64_exp(ua);
    u64 frac = f64_frac(ua) | (1ULL << 52);
    if (exp < 1023) return 0;
    if (exp >= 1023 + 31) return sign ? (-2147483647 - 1) : 2147483647;
    int shift = exp - 1023 - 52;
    u64 result = (shift >= 0) ? (frac << shift) : (frac >> (-shift));
    return sign ? -(int)result : (int)result;
}

FB_WEAK unsigned int __fixunsdfsi(double a) {
    u64 ua = f64_to_bits(a);
    if (f64_sign(ua)) return 0;
    int exp = f64_exp(ua);
    u64 frac = f64_frac(ua) | (1ULL << 52);
    if (exp < 1023) return 0;
    if (exp >= 1023 + 32) return 0xFFFFFFFFU;
    int shift = exp - 1023 - 52;
    u64 result = (shift >= 0) ? (frac << shift) : (frac >> (-shift));
    return (unsigned int)result;
}

FB_WEAK long long __fixdfdi(double a) {
    u64 ua = f64_to_bits(a);
    int sign = f64_sign(ua);
    int exp = f64_exp(ua);
    u64 frac = f64_frac(ua) | (1ULL << 52);
    if (exp < 1023) return 0;
    if (exp >= 1023 + 63) return sign ? (long long)(1ULL << 63) : (long long)((1ULL << 63) - 1);
    int shift = exp - 1023 - 52;
    u64 result = (shift >= 0) ? (frac << shift) : (frac >> (-shift));
    return sign ? -(long long)result : (long long)result;
}

FB_WEAK unsigned long long __fixunsdfdi(double a) {
    u64 ua = f64_to_bits(a);
    if (f64_sign(ua)) return 0;
    int exp = f64_exp(ua);
    u64 frac = f64_frac(ua) | (1ULL << 52);
    if (exp < 1023) return 0;
    if (exp >= 1023 + 64) return ~0ULL;
    int shift = exp - 1023 - 52;
    u64 result = (shift >= 0) ? (frac << shift) : (frac >> (-shift));
    return result;
}
