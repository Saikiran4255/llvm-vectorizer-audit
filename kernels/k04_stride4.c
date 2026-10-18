/* Stride 4. Vectorisable in principle but each vector lane costs a separate
 * cache line, so the cost model has to weigh an interleaved access against
 * scalar. A common case where firing is a mistake. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k04_stride4", 1.0, 12.0, "stride-4 access" };

void kernel_setup(long n) {
    size_t sz = (size_t)n * 4 * sizeof(float);
    a = aligned_alloc(64, sz); b = aligned_alloc(64, sz); c = aligned_alloc(64, sz);
    for (long i = 0; i < n * 4; i++) { a[i] = (float)i; b[i] = 1.0f; c[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *restrict cc, const float *restrict aa, const float *restrict bb, long n) {
    for (long i = 0; i < n; i++) cc[i * 4] = aa[i * 4] + bb[i * 4];
}
double kernel_run(long n) { body(c, a, b, n); return (double)c[(n / 2) * 4]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
