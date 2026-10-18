#!/usr/bin/env python3
"""Calibrate the machine, place every kernel on its roofline, classify the
vectoriser's decision.

The classification is the point of the project. A speedup table on its own
cannot distinguish "the vectoriser was wrong" from "the kernel was already
bandwidth-bound and no amount of vectorisation would have helped", and those
two findings call for completely different responses from a developer.

Buckets
-------
correct_fire        vectorised, and it paid
no_gain_memory      vectorised, gained nothing, and the kernel sits below the
                    memory roof so no gain was available: the cost model is not
                    wrong about legality, it is simply blind to bandwidth
no_gain_compute     vectorised, gained nothing, yet headroom existed: a genuine
                    cost-model or codegen miss
fixable_bail        refused, but forcing the vectoriser is faster: the refusal
                    cost real performance
correct_refusal     refused, and forcing it does not help or is illegal
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
CAL = ROOT / "calibrate"

# The configuration a developer actually gets by default on their own machine.
DEFAULT_CFG = "O3_native"
BASELINE_CFG = "O3_novec"
FORCED_CFG = "O3_native_force"
FFM_CFG = "O3_native_ffm"

# A speedup below this is treated as noise rather than a gain. Chosen to sit
# above the run-to-run spread observed on the measurement host; it is printed
# in the report so a reader can judge it against the reported RSD.
GAIN_THRESHOLD = 1.15
NOISE_BAND = 1.05


def calibrate(cc: str, bw_elems: int, flop_iters: int) -> dict:
    out = {}
    bw_bin, pf_bin = RESULTS / "_bw", RESULTS / "_pf"
    subprocess.run([cc, "-O3", "-march=native", "-o", str(bw_bin),
                    str(CAL / "bandwidth.c")], check=True)
    subprocess.run([cc, "-O3", "-march=native", "-funroll-loops", "-o", str(pf_bin),
                    str(CAL / "peakflops.c")], check=True)
    for binary, args in ((bw_bin, [str(bw_elems), "7"]),
                         (pf_bin, [str(flop_iters), "3"])):
        res = subprocess.run([str(binary), *args], capture_output=True, text=True, check=True)
        out.update(dict(ln.split("=", 1) for ln in res.stdout.splitlines() if "=" in ln))
    bw_bin.unlink(missing_ok=True)
    pf_bin.unlink(missing_ok=True)
    out = {k: float(v) if _isnum(v) else v for k, v in out.items()}
    bw = out["triad_gbytes_per_s"]
    pk = out["scalar_fma_gflops"]
    # The ridge point: arithmetic intensity at which the two roofs meet. Left of
    # it a kernel is bandwidth-bound and vector width cannot help it.
    out["ridge_flops_per_byte"] = pk / bw if bw else float("nan")
    return out


def _isnum(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def load(raw: Path) -> dict[str, dict[str, dict]]:
    by_kernel: dict[str, dict[str, dict]] = {}
    with raw.open() as f:
        for row in csv.DictReader(f):
            by_kernel.setdefault(row["kernel"], {})[row["config"]] = row
    return by_kernel


def classify(k: str, cfgs: dict[str, dict], cal: dict) -> dict:
    base = cfgs.get(BASELINE_CFG)
    dflt = cfgs.get(DEFAULT_CFG)
    forced = cfgs.get(FORCED_CFG)
    ffm = cfgs.get(FFM_CFG)
    if not (base and dflt) or not float(base["p50_s"]) or not float(dflt["p50_s"]):
        return {"kernel": k, "bucket": "no_data"}

    t_base, t_dflt = float(base["p50_s"]), float(dflt["p50_s"])
    speedup = t_base / t_dflt
    claimed = dflt["vectorized_claim"] == "1"
    packed = int(dflt["packed_ops"]) > 0

    n = float(dflt["n"]) or 1.0
    fpe, bpe = float(dflt["flops_per_elem"]), float(dflt["bytes_per_elem"])
    ai = fpe / bpe if bpe else float("nan")
    achieved_gflops = (fpe * n) / t_dflt / 1e9
    achieved_gbs = (bpe * n) / t_dflt / 1e9

    # Attainable performance at this arithmetic intensity, from the measured
    # ceilings rather than datasheet numbers.
    roof_gflops = min(cal["scalar_fma_gflops"], cal["triad_gbytes_per_s"] * ai)
    roof_frac = achieved_gflops / roof_gflops if roof_gflops else float("nan")
    memory_bound = ai < cal["ridge_flops_per_byte"]

    # Exceeding the roof is not an error, it is evidence that the kernel is not
    # being served from DRAM. The analytic intensity counts unique bytes, so a
    # working set that fits in last-level cache is supplied at cache bandwidth
    # while the ceiling was measured against DRAM. Such a point is flagged
    # rather than silently clipped, because the correct response is to grow the
    # working set, not to adjust the number.
    cache_resident = (not math.isnan(roof_frac)) and roof_frac > 1.10
    working_set_bytes = n * bpe

    forced_gain = (t_dflt / float(forced["p50_s"])
                   if forced and float(forced.get("p50_s") or 0) else float("nan"))
    ffm_gain = (t_dflt / float(ffm["p50_s"])
                if ffm and float(ffm.get("p50_s") or 0) else float("nan"))

    if claimed and packed:
        if speedup >= GAIN_THRESHOLD:
            bucket = "correct_fire"
        elif speedup <= NOISE_BAND:
            bucket = "no_gain_memory" if memory_bound else "no_gain_compute"
        else:
            bucket = "marginal_fire"
    else:
        improved_by_force = (not math.isnan(forced_gain)) and forced_gain >= GAIN_THRESHOLD
        improved_by_ffm = (not math.isnan(ffm_gain)) and ffm_gain >= GAIN_THRESHOLD
        bucket = "fixable_bail" if (improved_by_force or improved_by_ffm) else "correct_refusal"

    return {
        "kernel": k,
        "property": dflt["property"],
        "bucket": bucket,
        "claimed_vectorized": int(claimed),
        "packed_ops": int(dflt["packed_ops"]),
        "vf": dflt["vf"],
        "interleave": dflt["interleave"],
        "widest_vector": dflt["widest_vector"],
        "speedup_vs_scalar": round(speedup, 3),
        "forced_gain_vs_default": None if math.isnan(forced_gain) else round(forced_gain, 3),
        "ffastmath_gain_vs_default": None if math.isnan(ffm_gain) else round(ffm_gain, 3),
        "arithmetic_intensity": round(ai, 4),
        "achieved_gflops": round(achieved_gflops, 3),
        "achieved_gbytes_per_s": round(achieved_gbs, 3),
        "roofline_gflops": round(roof_gflops, 3),
        "pct_of_roofline": round(100 * roof_frac, 1),
        "memory_bound": int(memory_bound),
        "cache_resident_suspect": int(cache_resident),
        "working_set_bytes": int(working_set_bytes),
        "rsd_pct_default": float(dflt["rsd_pct"]),
        "blocking_reason": dflt["remark_text"][:180],
    }


def plot(rows: list[dict], cal: dict, out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable, skipping plot", file=sys.stderr)
        return

    bw, pk = cal["triad_gbytes_per_s"], cal["scalar_fma_gflops"]
    ridge = cal["ridge_flops_per_byte"]

    xs = [10 ** (e / 20) for e in range(-60, 41)]   # 0.001 .. 100 FLOP/byte
    roof = [min(pk, bw * x) for x in xs]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(xs, roof, linewidth=2, color="#333333", label="measured roofline")
    ax.axvline(ridge, linestyle="--", linewidth=1, color="#888888")
    ax.annotate(f"ridge {ridge:.2f} FLOP/byte", (ridge, pk * 0.30),
                rotation=90, va="bottom", ha="right", fontsize=8, color="#555555")

    style = {
        "correct_fire":    ("#1f6f3f", "o", "vectorised and gained"),
        "no_gain_memory":  ("#b07d00", "s", "vectorised, bandwidth-bound"),
        "no_gain_compute": ("#9b1c1c", "D", "vectorised, no gain, headroom existed"),
        "marginal_fire":   ("#6b6b6b", "o", "vectorised, marginal"),
        "fixable_bail":    ("#1f4e9b", "^", "refused, forcing was faster"),
        "correct_refusal": ("#6b6b6b", "x", "refused, correctly"),
    }
    seen = set()
    for r in rows:
        if r["bucket"] == "no_data":
            continue
        colour, marker, label = style.get(r["bucket"], ("#000000", ".", r["bucket"]))
        ax.scatter(r["arithmetic_intensity"], r["achieved_gflops"],
                   c=colour, marker=marker, s=70, zorder=3,
                   label=label if label not in seen else None)
        seen.add(label)
        ax.annotate(r["kernel"].split("_", 1)[0],
                    (r["arithmetic_intensity"], r["achieved_gflops"]),
                    textcoords="offset points", xytext=(5, 4), fontsize=7)

    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("arithmetic intensity (FLOP / byte, analytic)")
    ax.set_ylabel("achieved performance (GFLOP/s)")
    ax.set_title(f"LLVM loop vectoriser on {cal.get('host','this host')}\n"
                 f"measured ceilings: {bw:.1f} GB/s, {pk:.1f} GFLOP/s")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"wrote {out}", file=sys.stderr)


def markdown(rows: list[dict], cal: dict, env: dict) -> str:
    order = ["correct_fire", "no_gain_memory", "no_gain_compute",
             "marginal_fire", "fixable_bail", "correct_refusal", "no_data"]
    rows = sorted(rows, key=lambda r: (order.index(r["bucket"]) if r["bucket"] in order else 99,
                                       r["kernel"]))
    L = []
    L.append("| kernel | property | verdict | VF | speedup vs scalar | AI | % of roof | note |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r["bucket"] == "no_data":
            L.append(f"| {r['kernel']} | | no data | | | | | |")
            continue
        note = ""
        if r["bucket"] == "fixable_bail":
            note = r["blocking_reason"][:70]
        elif r["bucket"] == "no_gain_memory":
            note = "below ridge, no gain available"
        if r.get("cache_resident_suspect"):
            note = (note + "; " if note else "") + "above DRAM roof: cache-resident, grow working set"
        elif r["bucket"] == "correct_refusal" and r["blocking_reason"]:
            note = r["blocking_reason"][:70]
        L.append(
            f"| `{r['kernel']}` | {r['property']} | **{r['bucket']}** | "
            f"{r['vf'] or '-'} | {r['speedup_vs_scalar']:.2f}x | "
            f"{r['arithmetic_intensity']:.3f} | {r['pct_of_roofline']:.0f}% | {note} |"
        )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    head = [
        f"Host: {env.get('cpu_model','?')} ({env.get('cpu_count','?')} cores), "
        f"{env.get('kernel','?')}",
        f"Compiler: {env.get('compiler','?')}",
        f"Measured ceilings: {cal['triad_gbytes_per_s']:.2f} GB/s triad, "
        f"{cal['scalar_fma_gflops']:.2f} GFLOP/s FMA, "
        f"ridge {cal['ridge_flops_per_byte']:.3f} FLOP/byte",
        f"Gain threshold: {GAIN_THRESHOLD}x, noise band {NOISE_BAND}x",
        f"Verdicts: {summary}",
        f"Working set per kernel: "
        f"{min((r.get('working_set_bytes',0) for r in rows if r.get('working_set_bytes')), default=0)/1e6:.1f}"
        f" to "
        f"{max((r.get('working_set_bytes',0) for r in rows if r.get('working_set_bytes')), default=0)/1e6:.1f}"
        f" MB (points above the roof are cache-resident, see Limitations)",
        "",
    ]
    return "\n".join(head + L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=str(RESULTS / "raw.csv"))
    ap.add_argument("--cc", default="clang")
    ap.add_argument("--bw-elems", type=int, default=1 << 24)
    ap.add_argument("--flop-iters", type=int, default=20_000_000)
    ap.add_argument("--skip-calibration", action="store_true",
                    help="reuse results/calibration.json")
    args = ap.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    cal_path = RESULTS / "calibration.json"
    if args.skip_calibration and cal_path.exists():
        cal = json.loads(cal_path.read_text())
    else:
        cal = calibrate(args.cc, args.bw_elems, args.flop_iters)
        cal_path.write_text(json.dumps(cal, indent=2))
    print(json.dumps(cal, indent=2), file=sys.stderr)

    env_path = RESULTS / "environment.json"
    env = json.loads(env_path.read_text()) if env_path.exists() else {}

    by_kernel = load(Path(args.raw))
    rows = [classify(k, cfgs, cal) for k, cfgs in sorted(by_kernel.items())]

    with (RESULTS / "verdicts.csv").open("w", newline="") as f:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    (RESULTS / "verdicts.md").write_text(markdown(rows, cal, env))
    plot(rows, cal, RESULTS / "roofline.png")
    print(markdown(rows, cal, env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
