/* Two unqualified pointers that may overlap. LLVM must either refuse or emit a
 * runtime alias check with a scalar fallback. Paired with k11, which is the
 * same loop with restrict: the delta is the cost of not telling the compiler
 * something you already know. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b, *c;
const kernel_meta_t KERNEL_META = { "k10_alias_noqual", 1.0, 12.0, "possible aliasing, no restrict" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    c = aligned_alloc(64, (size_t)n * sizeof *c);
    for (long i = 0; i < n; i++) { a[i] = (float)i; b[i] = 1.0f; c[i] = 0.0f; }
}
__attribute__((noinline))
static void body(float *cc, const float *aa, const float *bb, long n) {
    for (long i = 0; i < n; i++) cc[i] = aa[i] * bb[i];
}
double kernel_run(long n) { body(c, a, b, n); return (double)c[n / 2]; }
void kernel_teardown(void) { free(a); free(b); free(c); }
#include "bench.h"
