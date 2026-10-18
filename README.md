# llvm-vec-audit

A benchmark harness that audits LLVM's loop vectoriser: what it claims, what it
actually emitted, what the hardware did, and whether any of it was worth doing.

Most "`-O2` vs `-O3`" comparisons stop at a speedup table. A speedup table
cannot tell you the difference between *the vectoriser made a bad decision* and
*the loop was already bandwidth-bound and no decision could have helped*, and
those two findings call for completely different responses. This harness
separates them by placing every result on a roofline built from ceilings
measured on the same machine, in the same run.

## What it measures

Three independent sources of evidence per (kernel, configuration):

| layer | mechanism | why |
|---|---|---|
| what the compiler claims | `-fsave-optimization-record`, filtered to the hot function | LLVM states its own vectorisation factor, interleave count, and when it refuses, the reason |
| what the binary contains | `objdump` of the hot function, packed-operation mnemonics | a `Passed` remark does not guarantee packed instructions survived later passes |
| what the hardware did | in-process timing, p50/p99 over N repetitions, pinned core | the only layer that can contradict the other two |

The second layer exists because the first can mislead. Counting `xmm` register
references is not enough either: on x86-64 **scalar** floating point also uses
`xmm`, so the scalar control appears "vectorised" if you count registers. The
harness counts packed mnemonics (`ps`/`pd` suffixes, packed integer ops) and
subtracts scalar ones (`ss`/`sd`).

## Configurations

| name | flags | purpose |
|---|---|---|
| `O2` | `-O2` | conservative cost model |
| `O3` | `-O3` | aggressive, generic target |
| `O3_native` | `-O3 -march=native` | the cost model now knows the real vector width |
| `O3_novec` | `-O3 -march=native -fno-vectorize -fno-slp-vectorize` | **scalar control**, every speedup is measured against this |
| `O3_native_ffm` | `+ -ffast-math` | permits FP reassociation, which reductions need |
| `O3_native_force` | `+ -mllvm -force-vector-width=8` | overrides the cost model, so we can measure what it declined |

`O3_native_force` is the lever that makes the classification possible: where
forcing is faster than the default, the cost model's refusal cost real
performance.

## The classification

Each kernel lands in exactly one bucket:

- **`correct_fire`** — vectorised, and it paid (≥1.15x over scalar)
- **`no_gain_memory`** — vectorised, gained nothing, and sits below the ridge
  point, so no gain was available. The cost model is not wrong about legality;
  it is blind to bandwidth.
- **`no_gain_compute`** — vectorised, gained nothing, yet headroom existed. A
  genuine cost-model or codegen miss.
- **`fixable_bail`** — refused, but forcing it (or relaxing FP semantics) is
  faster. The refusal was legal and expensive.
- **`correct_refusal`** — refused, and forcing does not help or is illegal.

A harness that reports a true loop-carried dependence as a "missed
opportunity" is measuring itself wrong rather than the compiler, which is why
`k14` is in the corpus as a control.

## Kernels

Each isolates one property the vectoriser reasons about. Paired kernels move
exactly one variable.

| kernel | property under test |
|---|---|
| `k01_unit_stride_add` | baseline: unit-stride, non-aliasing |
| `k02_dot_reduction` | float reduction, needs reassociation |
| `k03_stencil3` | overlapping unit-stride reads |
| `k04_stride4` | stride-4 access |
| `k05_gather_idx` | indirect gather through an index array |
| `k06_aos_sum` / `k07_soa_sum` | **layout pair**: array-of-structs vs struct-of-arrays, identical arithmetic |
| `k08_cond_body` | data-dependent branch, predication |
| `k09_early_exit` | early exit, trip count unknown before the loop runs |
| `k10_alias_noqual` / `k11_alias_restrict` | **aliasing pair**: same loop, the only difference is the `restrict` promise |
| `k12_fixedpoint_sat` | int16 saturating MAC idiom |
| `k13_double_add` | `k01` in double: half the lanes, double the traffic |
| `k14_loop_carried` | true dependence — control, must refuse |

## Methodology

Everything here exists to remove a known source of variance.

- **Core pinning** via `sched_setaffinity`. A migrating thread mixes two caches
  into one number, which is the most common way a microbenchmark lies. A failed
  pin is recorded in the output rather than ignored.
- **Warm-up** before measurement, so first-touch page faults, cache and branch
  predictor state, and any frequency ramp land outside the samples.
- **Percentiles, not means.** p50 is reported as the headline, p99 alongside it,
  and the relative standard deviation is in every row so a reader can judge
  whether a 1.1x difference is real.
- **Governor recorded**, not assumed. The harness reads
  `scaling_governor` and prints it; where it is unavailable, that is recorded
  too.
- **Checksums returned** from every kernel, so no loop can be eliminated as
  dead code. A benchmark that measures nothing is worse than no benchmark.
- **Hot loop isolated** in a `noinline` function called `body` in every kernel,
  so optimisation records and disassembly can both be filtered to it. Without
  that filter the records are dominated by `setup` and `main`.
- **Compiler pinned** in Docker, so a reader reproduces these numbers rather
  than their own.

## Limitations

Stated explicitly, because a benchmark that does not list these is not telling
you the whole story.

1. **Hardware counters are absent from the reference run.** `perf` was not
   available on the measurement host, so cache-miss and IPC attribution is
   missing. The harness detects this and records `perf_available: false`.
   Vectorisation is verified from the disassembly instead, which is sufficient
   for the classification but not for explaining *why* a kernel missed its roof.
2. **Working sets partly fit in cache.** At the default size several kernels
   exceed the DRAM roofline, which is not an error: it is evidence they are
   being served at cache bandwidth while the ceiling was measured against DRAM.
   These are flagged `cache_resident_suspect`. The correct response is to grow
   `-n` past last-level cache, not to adjust the ceiling.
3. **Arithmetic intensity is analytic, not measured.** It counts unique bytes
   per element, not actual traffic. For kernels with reuse (`k03`) the real
   intensity is higher than stated. Measuring traffic needs counters, see (1).
4. **`-fno-vectorize` is an imperfect control.** It disables the loop and SLP
   vectorisers but does not perfectly isolate vectorisation from every other
   `-O3` decision, so a small part of any reported speedup may not be
   vectorisation. `k09` shows this clearly.
5. **Single host, single microarchitecture.** AVX2, no AVX-512. Conclusions
   about vector width do not transfer to a machine with `zmm` registers.
6. **Two cores, shared virtual host.** Observed RSD reaches 10 to 40% on some
   kernels. On quiet bare metal it should be far lower; the reported RSD is the
   honest figure for this host, not a target.

## Reproducing

```sh
make            # build and run everything, then analyse
make bench      # measurement only
make analyze    # re-classify from an existing results/raw.csv
make docker     # pinned clang, reproducible numbers
```

Useful knobs:

```sh
python3 runner.py -n 16777216 --reps 101 --cpu 3 --keep-records
python3 analyze.py --skip-calibration
```

Grow `-n` until no kernel is flagged `cache_resident_suspect`.

## Output

- `results/raw.csv` — every (kernel, config) with claim, disassembly evidence and timings
- `results/verdicts.csv` / `verdicts.md` — the classification table
- `results/roofline.png` — the plot, points coloured by verdict
- `results/calibration.json` — measured ceilings and the ridge point
- `results/environment.json` — host, compiler, tool availability
- `results/records/` — raw optimisation records, with `--keep-records`

## Findings on the reference host

Reference run: Intel Xeon @ 2.80 GHz, 2 cores, clang 18.1.3, AVX2, `n = 2^21`,
31 repetitions. Measured ceilings 12.9 GB/s triad and 10.6 GFLOP/s FMA, giving a
ridge point of **0.82 FLOP/byte**.

**A caution that belongs before the findings, not after them.** This host is a
shared two-core virtual machine. Running the full matrix twice moved individual
speedups by up to 0.3x and reclassified two kernels across the 1.15x gain
threshold. The claims below are restricted to what held across repeated runs;
anything that moved between them is reported as a range rather than a number.
Re-run on quiet bare metal before quoting any single figure.

**1. The entire corpus is bandwidth-bound, which no speedup table would have
told you.** Every kernel sits below the 0.82 FLOP/byte ridge, the highest at
0.375. That single fact reframes every other result: these loops do not have a
compute problem, so vector width was never the lever. This is the finding the
roofline exists to produce and the reason the project is not just a flag
comparison.

**2. Stride-4 access reaches exactly the fraction of bandwidth you would
predict, and vectorising it changes nothing.** `k04_stride4` vectorises at VF=4
and lands at **0.96 to 1.00x** against scalar, at **23% of its roofline**, stable
across runs. Touching one float in every four wastes three quarters of each
64-byte line, so effective bandwidth should be about a quarter of peak, and 23%
is what was measured. The prediction and the measurement agree, which is the
strongest evidence in the corpus that the harness is measuring what it claims.

**3. Vectorising an indirect gather never paid, and sometimes cost.** Across
runs `k05_gather_idx` vectorised at VF=8 and returned between **0.65x and
0.96x** — never a gain, occasionally a significant loss, at 17 to 23% of its
roof. The cost model priced a gather below eight scalar loads; on this
microarchitecture that was not borne out. The spread is why this is stated as a
direction rather than a figure.

**4. The legally correct refusal on a float reduction is recoverable by the
developer.** `k02_dot_reduction` is refused at `-O3`, correctly: vectorising
reassociates floating-point addition and changes the result. `-ffast-math`
recovers a real gain, which is why the harness labels it `fixable_bail` rather
than `correct_refusal`. The compiler is not wrong, it is waiting to be told that
reassociation is acceptable.

**5. Data layout moved more performance than any compiler flag here.**
`k06_aos_sum` and `k07_soa_sum` compute the same thing and both vectorise at
VF=8. Struct-of-arrays returned 1.36 to 1.43x; array-of-structs returned 1.01 to
1.06x. Same arithmetic, same vector width, different layout, and the layout won.

**The two control kernels behave correctly.** `k14_loop_carried` is refused with
`unsafe dependent memory operations in loop`, and `k09_early_exit` is refused for
an unknown trip count. A harness that scored either as a missed opportunity
would be measuring itself rather than the compiler.

The full table is in [`results/verdicts.md`](results/verdicts.md) and the plot in
[`results/roofline.png`](results/roofline.png).

## Why I built it

I kept seeing `-O3` and hand-written intrinsics reached for as though
vectorisation were free, and I wanted to know when the compiler is actually
right. Building the harness changed how I read a profile: the result that
surprised me was how often the vectoriser fires correctly and gains nothing,
because LLVM's cost model reasons about instruction counts and latencies and
has no model of memory bandwidth at all. Three to four of the fourteen
kernels here vectorised cleanly and bought nothing, and one of those was
sometimes negative. None of that is visible without a roofline next to the
speedup, which is why the roofline is the point of the harness rather than a
decoration on it.

## Licence

MIT.
