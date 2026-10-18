/* STREAM-style triad, used to measure attainable bandwidth on this machine
 * rather than quoting a vendor figure. The roofline ceiling has to come from
 * the same hardware, compiler and run conditions as the kernels, or the
 * comparison is meaningless.
 *
 * Working set is forced well past last-level cache, and the result reported is
 * the best of several repetitions, since the maximum attainable bandwidth is
 * what the ceiling represents.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}

int main(int argc, char **argv) {
    long n = (argc > 1) ? atol(argv[1]) : (1L << 25);   /* 256 MB of doubles */
    int reps = (argc > 2) ? atoi(argv[2]) : 10;
    double *a = aligned_alloc(64, n * sizeof *a);
    double *b = aligned_alloc(64, n * sizeof *b);
    double *c = aligned_alloc(64, n * sizeof *c);
    if (!a || !b || !c) { fprintf(stderr, "alloc failed\n"); return 1; }
    for (long i = 0; i < n; i++) { a[i] = 1.0; b[i] = 2.0; c[i] = 0.0; }

    double best = 0.0;
    for (int r = 0; r < reps; r++) {
        double t0 = now();
        for (long i = 0; i < n; i++) c[i] = a[i] + 3.0 * b[i];
        double dt = now() - t0;
        /* Triad touches 3 arrays: two reads and one write. The write is counted
         * once; on a write-allocate cache it also costs a read, which is why
         * this is reported as "attainable" rather than theoretical. */
        double gbs = (3.0 * n * sizeof(double)) / dt / 1e9;
        if (gbs > best) best = gbs;
    }
    printf("triad_gbytes_per_s=%.4f\n", best);
    printf("bytes_counted_per_elem=%zu\n", 3 * sizeof(double));
    free(a); free(b); free(c);
    return 0;
}
