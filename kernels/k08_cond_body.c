/* Data-dependent branch in the body. Vectorising requires predication (masked
 * ops or select), whose profitability depends on the taken fraction. Here it
 * is deterministically 50%, the worst case for a branch predictor and the case
 * where predication should win. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *c;
const kernel_meta_t KERNEL_META = { "k08_cond_body", 1.0, 8.0, "data-dependent branch, predication" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (i % 2) ? 1.0f : -1.0f; c[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *restrict cc, const float *restrict aa, long n) {
    for (long i = 0; i < n; i++) { if (aa[i] > 0.0f) cc[i] = aa[i] * 3.0f; }
}
double kernel_run(long n) { body(c, a, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(c); }
#include "bench.h"
