Host: Intel(R) Xeon(R) Processor @ 2.80GHz (2 cores), 6.18.44-fc-v139
Compiler: Ubuntu clang version 18.1.3 (1ubuntu1)
Measured ceilings: 12.93 GB/s triad, 10.62 GFLOP/s FMA, ridge 0.821 FLOP/byte
Gain threshold: 1.15x, noise band 1.05x
Verdicts: 7 correct_fire, 2 correct_refusal, 1 fixable_bail, 4 no_gain_memory
Working set per kernel: 8.4 to 50.3 MB (points above the roof are cache-resident, see Limitations)

| kernel | property | verdict | VF | speedup vs scalar | AI | % of roof | note |
|---|---|---|---|---|---|---|---|
| `k01_unit_stride_add` | unit-stride, non-aliasing | **correct_fire** | 8 | 1.21x | 0.083 | 119% | above DRAM roof: cache-resident, grow working set |
| `k03_stencil3` | overlapping unit-stride reads | **correct_fire** | 8 | 3.18x | 0.375 | 151% | above DRAM roof: cache-resident, grow working set |
| `k07_soa_sum` | struct-of-arrays layout | **correct_fire** | 8 | 1.43x | 0.125 | 191% | above DRAM roof: cache-resident, grow working set |
| `k08_cond_body` | data-dependent branch, predication | **correct_fire** | 8 | 1.85x | 0.125 | 218% | above DRAM roof: cache-resident, grow working set |
| `k11_alias_restrict` | same loop with restrict | **correct_fire** | 8 | 1.19x | 0.083 | 119% | above DRAM roof: cache-resident, grow working set |
| `k12_fixedpoint_sat` | int16 saturating MAC idiom | **correct_fire** | 16 | 1.63x | 0.333 | 146% | above DRAM roof: cache-resident, grow working set |
| `k13_double_add` | double precision, half vector width | **correct_fire** | 4 | 1.26x | 0.042 | 120% | above DRAM roof: cache-resident, grow working set |
| `k04_stride4` | stride-4 access | **no_gain_memory** | 4 | 0.96x | 0.083 | 23% | below ridge, no gain available |
| `k05_gather_idx` | indirect gather via index array | **no_gain_memory** | 8 | 0.96x | 0.083 | 23% | below ridge, no gain available |
| `k06_aos_sum` | array-of-structs layout | **no_gain_memory** | 8 | 1.01x | 0.050 | 84% | below ridge, no gain available |
| `k10_alias_noqual` | possible aliasing, no restrict | **no_gain_memory** | 8 | 1.02x | 0.083 | 124% | below ridge, no gain available; above DRAM roof: cache-resident, grow working set |
| `k02_dot_reduction` | float reduction, reassociation required | **fixable_bail** | - | 1.04x | 0.250 | 47% |  |
| `k09_early_exit` | early exit, unknown trip count | **correct_refusal** | - | 1.07x | 0.250 | 63% | loop not vectorized: |
| `k14_loop_carried` | true loop-carried dependence | **correct_refusal** | - | 0.96x | 0.250 | 45% | loop not vectorized: unsafe dependent memory operations in loop. Use # |
