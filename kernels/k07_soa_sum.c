/* Struct-of-arrays counterpart to k06. Identical arithmetic, contiguous
 * access. The delta between k06 and k07 is the cost of layout alone. */
#include <stdlib.h>
#include "kernel.h"
static float *x, *out;
const kernel_meta_t KERNEL_META = { "k07_soa_sum", 1.0, 8.0, "struct-of-arrays layout" };

void kernel_setup(long n) {
    x   = aligned_alloc(64, (size_t)n * sizeof *x);
    out = aligned_alloc(64, (size_t)n * sizeof *out);
    for (long i = 0; i < n; i++) { x[i] = (float)i; out[i] = 0; }
}
__attribute__((noinline))
static void body(float *restrict o, const float *restrict xx, long n) {
    for (long i = 0; i < n; i++) o[i] = xx[i] * 2.0f;
}
double kernel_run(long n) { body(out, x, n); return (double)out[n / 2]; }
void kernel_teardown(void) { free(x); free(out); }
#include "bench.h"
