/* k11: identical to k10 but with restrict. The only variable moved between the
 * two is the aliasing promise, which is what makes the comparison meaningful. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k11_alias_restrict", 1.0, 12.0, "same loop with restrict" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (float)i; b[i] = 1.0f; c[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *restrict cc, const float *restrict aa, const float *restrict bb, long n) {
    for (long i = 0; i < n; i++) cc[i] = aa[i] * bb[i];
}
double kernel_run(long n) { body(c, a, b, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
