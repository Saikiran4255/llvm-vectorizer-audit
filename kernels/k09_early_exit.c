/* Early exit. The trip count is not known before the loop runs, so classic
 * loop vectorisation does not apply. A refusal here is correct and the harness
 * must not score it as a miss. */
#include <stdlib.h>
#include "kernel.h"
static float *a;
const kernel_meta_t KERNEL_META = { "k09_early_exit", 1.0, 4.0, "early exit, unknown trip count" };

void kernel_setup(long n) {
    a = aligned_alloc(64, (size_t)n * sizeof *a);
    for (long i = 0; i < n; i++) a[i] = 0.0f;
    a[n - 1] = 1.0f;   /* worst case: scan the whole array */
}
__attribute__((noinline))
static long body(const float *restrict aa, long n) {
    for (long i = 0; i < n; i++) if (aa[i] > 0.5f) return i;
    return -1;
}
double kernel_run(long n) { return (double)body(a, n); }
void kernel_teardown(void) { free(a); }
#include "bench.h"
