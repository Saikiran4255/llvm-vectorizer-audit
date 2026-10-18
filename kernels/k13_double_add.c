/* k01 in double precision. Same loop, half the lanes per vector register, so
 * the speedup ceiling halves while the memory traffic doubles. Isolates
 * element width as the single variable. */
#include <stdlib.h>
#include "kernel.h"
static double *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k13_double_add", 1.0, 24.0, "double precision, half vector width" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (double)i; b[i] = 0.5; c[i] = 0.0; }
}
__attribute__((noinline))
static void body(double *restrict cc, const double *restrict aa, const double *restrict bb, long n) {
    for (long i = 0; i < n; i++) cc[i] = aa[i] + bb[i];
}
double kernel_run(long n) { body(c, a, b, n); return c[n / 2]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
