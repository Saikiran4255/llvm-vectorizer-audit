/* Minimal benchmarking harness: pinning, warm-up, repetitions, percentiles.
 *
 * Deliberately small and dependency-free so the measurement path is auditable.
 * Every design choice here exists to remove a known source of variance; see
 * README "Methodology" for what is controlled and what is not.
 */
#ifndef BENCH_H
#define BENCH_H

/* _GNU_SOURCE is supplied by the build (-D_GNU_SOURCE): the kernel TU
   includes libc headers before this file, so defining it here is too late. */
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>

#include "kernel.h"

static inline double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + 1e-9 * (double)ts.tv_nsec;
}

static int cmp_double(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

/* Pin to one core. Measuring on a migrating thread mixes two caches into one
 * number, which is the most common way a microbenchmark lies. */
static inline int pin_to_cpu(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return sched_setaffinity(0, sizeof(set), &set);
}

static inline void report_env(void) {
    FILE *f = fopen("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "r");
    char gov[64] = "unavailable";
    if (f) { if (!fgets(gov, sizeof gov, f)) strcpy(gov, "unreadable"); fclose(f); }
    gov[strcspn(gov, "\n")] = 0;
    fprintf(stderr, "env.governor=%s\n", gov);
}

int main(int argc, char **argv) {
    long n     = (argc > 1) ? atol(argv[1]) : (1L << 22);
    int  reps  = (argc > 2) ? atoi(argv[2]) : 51;
    int  warm  = (argc > 3) ? atoi(argv[3]) : 5;
    int  cpu   = (argc > 4) ? atoi(argv[4]) : 0;

    if (pin_to_cpu(cpu) != 0)
        fprintf(stderr, "warn.pin_failed=1\n");   /* recorded, not fatal */
    report_env();

    kernel_setup(n);

    /* Warm-up: first-touch page faults, cache and branch predictor state, and
     * any frequency ramp all land here rather than in the measured samples. */
    volatile double sink = 0.0;
    for (int i = 0; i < warm; i++) sink += kernel_run(n);

    double *t = malloc((size_t)reps * sizeof *t);
    for (int i = 0; i < reps; i++) {
        double t0 = now_sec();
        sink += kernel_run(n);
        t[i] = now_sec() - t0;
    }
    qsort(t, (size_t)reps, sizeof *t, cmp_double);

    double p50 = t[reps / 2];
    double p99 = t[(int)((double)(reps - 1) * 0.99)];
    double min = t[0];
    double mean = 0.0;
    for (int i = 0; i < reps; i++) mean += t[i];
    mean /= reps;
    double var = 0.0;
    for (int i = 0; i < reps; i++) var += (t[i] - mean) * (t[i] - mean);
    double sd = (reps > 1) ? sqrt(var / (reps - 1)) : 0.0;

    /* Machine readable: the runner parses these lines, nothing else. */
    printf("kernel=%s\n",        KERNEL_META.name);
    printf("property=%s\n",      KERNEL_META.property);
    printf("n=%ld\n",            n);
    printf("reps=%d\n",          reps);
    printf("p50_s=%.9f\n",       p50);
    printf("p99_s=%.9f\n",       p99);
    printf("min_s=%.9f\n",       min);
    printf("mean_s=%.9f\n",      mean);
    printf("sd_s=%.9f\n",        sd);
    printf("rsd_pct=%.4f\n",     mean > 0 ? 100.0 * sd / mean : 0.0);
    printf("flops_per_elem=%g\n", KERNEL_META.flops_per_elem);
    printf("bytes_per_elem=%g\n", KERNEL_META.bytes_per_elem);
    printf("checksum=%.6f\n",    (double)sink);

    free(t);
    kernel_teardown();
    return 0;
}
#endif
