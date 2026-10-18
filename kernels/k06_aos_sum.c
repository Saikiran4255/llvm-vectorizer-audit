/* Array-of-structs. Summing one field means a stride of sizeof(struct), so the
 * vectoriser must interleave. Paired with k07 (struct-of-arrays) to isolate
 * layout as the only difference: same arithmetic, same element count. */
#include <stdlib.h>
#include "kernel.h"
typedef struct { float x, y, z, w; } vec4_t;
static vec4_t *p; static float *out;
const kernel_meta_t KERNEL_META = { "k06_aos_sum", 1.0, 20.0, "array-of-structs layout" };

void kernel_setup(long n) {
    p   = aligned_alloc(64, (size_t)n * sizeof *p);
    out = aligned_alloc(64, (size_t)n * sizeof *out);
    for (long i = 0; i < n; i++) { p[i].x = (float)i; p[i].y = 1; p[i].z = 2; p[i].w = 3; out[i] = 0; }
}
__attribute__((noinline))
static void body(float *restrict o, const vec4_t *restrict q, long n) {
    for (long i = 0; i < n; i++) o[i] = q[i].x * 2.0f;
}
double kernel_run(long n) { body(out, p, n); return (double)out[n / 2]; }
void kernel_teardown(void) { free(p); free(out); }
#include "bench.h"
