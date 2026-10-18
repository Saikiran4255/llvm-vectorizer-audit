/* Baseline: unit-stride, no aliasing, trivially vectorisable.
 * Arithmetic intensity 1 FLOP / 12 bytes = 0.083, so this is firmly
 * bandwidth-bound and vectorisation is expected to buy little. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k01_unit_stride_add", 1.0, 12.0, "unit-stride, non-aliasing" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (float)i * 0.5f; b[i] = (float)i * 0.25f; c[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *restrict cc, const float *restrict aa, const float *restrict bb, long n) {
    for (long i = 0; i < n; i++) cc[i] = aa[i] + bb[i];
}
double kernel_run(long n) { body(c, a, b, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
