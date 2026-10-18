/* Three-point stencil: unit stride with overlapping reads. Vectorisable, and
 * the overlap means the real traffic is far below the naive byte count, which
 * is exactly why analytic intensity has to be stated rather than guessed. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b;
const kernel_meta_t KERNEL_META = { "k03_stencil3", 3.0, 8.0, "overlapping unit-stride reads" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)(n + 2) * sizeof *a);
    b = aligned_alloc(64, (size_t)(n + 2) * sizeof *b);
    for (long i = 0; i < n + 2; i++) { a[i] = (float)(i % 17); b[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *restrict bb, const float *restrict aa, long n) {
    for (long i = 1; i < n - 1; i++) bb[i] = (aa[i - 1] + aa[i] + aa[i + 1]) * 0.3333333f;
}
double kernel_run(long n) { body(b, a, n); return (double)b[n / 2]; }
void kernel_teardown(void) { free(a); free(b); }
#include "bench.h"
