/* True loop-carried dependence: element i reads the value written at i-1.
 * No legal vectorisation exists. Included as a control: a harness that reports
 * this as a missed opportunity is measuring itself wrong, not the compiler. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b;
const kernel_meta_t KERNEL_META = { "k14_loop_carried", 2.0, 8.0, "true loop-carried dependence" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    for (long i = 0; i < n; i++) { a[i] = 1.0f; b[i] = 0.001f; }
}
__attribute__((noinline))
static void body(float *restrict aa, const float *restrict bb, long n) {
    for (long i = 1; i < n; i++) aa[i] = aa[i - 1] * 0.5f + bb[i];
}
double kernel_run(long n) { body(a, b, n); return (double)a[n / 2]; }
void kernel_teardown(void) { free(a); free(b); }
#include "bench.h"
