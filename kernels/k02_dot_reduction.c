/* Reduction. Vectorising this reassociates floating-point addition, so it
 * requires -ffast-math or a pragma; at -O3 alone LLVM must refuse. That
 * refusal is correct, and the harness should record it as such. */
#include <stdlib.h>
#include "kernel.h"
static float *a, *b;
const kernel_meta_t KERNEL_META = { "k02_dot_reduction", 2.0, 8.0, "float reduction, reassociation required" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    b = aligned_alloc(64, (size_t)n * sizeof *b);
    for (long i = 0; i < n; i++) { a[i] = 1.0f / (float)(i + 1); b[i] = 2.0f; }
}
__attribute__((noinline))
static float body(const float *restrict aa, const float *restrict bb, long n) {
    float s = 0.0f;
    for (long i = 0; i < n; i++) s += aa[i] * bb[i];
    return s;
}
double kernel_run(long n) { return (double)body(a, b, n); }
void kernel_teardown(void) { free(a); free(b); }
#include "bench.h"
