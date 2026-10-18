/* Indirect gather. LLVM can emit a gather on AVX2 but the cost model usually
 * decides against it; whether that is right depends entirely on how scattered
 * the index array is, which the compiler cannot know. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *c; static int *idx;
const kernel_meta_t KERNEL_META = { "k05_gather_idx", 1.0, 12.0, "indirect gather via index array" };

void kernel_setup(long n) {
    a   = aligned_alloc(64, (size_t)n * sizeof *a);
    c   = aligned_alloc(64, (size_t)n * sizeof *c);
    idx = aligned_alloc(64, (size_t)n * sizeof *idx);
    for (long i = 0; i < n; i++) { a[i] = (float)i; c[i] = 0.0f; }
    /* Deterministic scatter: fixed stride through a large prime so the pattern
     * is reproducible across runs rather than dependent on an RNG seed. */
    for (long i = 0; i < n; i++) idx[i] = (int)((i * 7919L) % n);
}
__attribute__((noinline))
static void body(float *restrict cc, const float *restrict aa, const int *restrict ii, long n) {
    for (long i = 0; i < n; i++) cc[i] = aa[ii[i]] + 1.0f;
}
double kernel_run(long n) { body(c, a, idx, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(c); free(idx); }
#include "bench.h"
