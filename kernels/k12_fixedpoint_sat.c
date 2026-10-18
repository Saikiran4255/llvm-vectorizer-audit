/* Saturating fixed-point multiply-accumulate on int16. Saturation is a
 * branch-free clamp in C but maps to a single SIMD instruction; whether LLVM
 * recognises the idiom is the question. This is the kernel where hand-written
 * intrinsics most often still beat the auto-vectoriser. */
#include <stdlib.h>
#include <stdint.h>
#include "kernel.h"
static int16_t *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k12_fixedpoint_sat", 2.0, 6.0, "int16 saturating MAC idiom" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (int16_t)(i % 30000); b[i] = 300; c[i] = 0; }
}
__attribute__((noinline))
static void body(int16_t *restrict cc, const int16_t *restrict aa, const int16_t *restrict bb, long n) {
    for (long i = 0; i < n; i++) {
        int32_t t = ((int32_t)aa[i] * (int32_t)bb[i]) >> 15;
        t = t >  32767 ?  32767 : t;
        t = t < -32768 ? -32768 : t;
        cc[i] = (int16_t)t;
    }
}
double kernel_run(long n) { body(c, a, b, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
