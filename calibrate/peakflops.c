/* Measured compute ceiling: independent FMA chains, resident entirely in
 * registers, so no memory traffic can limit it. Several independent chains are
 * needed to cover the FMA latency; with one chain this measures latency rather
 * than throughput, which is the usual way a peak-FLOPS microbenchmark
 * understates the machine by a factor of four or more.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}

#define CHAINS 8

int main(int argc, char **argv) {
    long iters = (argc > 1) ? atol(argv[1]) : 200000000L;
    int reps = (argc > 2) ? atoi(argv[2]) : 5;
    double best = 0.0;
    for (int r = 0; r < reps; r++) {
        volatile double sink = 0.0;
        double acc[CHAINS], m = 1.0000001, add = 0.0000001;
        for (int i = 0; i < CHAINS; i++) acc[i] = (double)(i + 1);
        double t0 = now();
        for (long i = 0; i < iters; i++)
            for (int c = 0; c < CHAINS; c++) acc[c] = acc[c] * m + add;
        double dt = now() - t0;
        for (int i = 0; i < CHAINS; i++) sink += acc[i];
        /* 2 FLOPs per FMA, CHAINS FMAs per iteration. */
        double gflops = (2.0 * CHAINS * iters) / dt / 1e9;
        if (gflops > best) best = gflops;
        (void)sink;
    }
    printf("scalar_fma_gflops=%.4f\n", best);
    printf("chains=%d\n", CHAINS);
    return 0;
}
