#!/usr/bin/env python3
"""Compile, interrogate and time every kernel across the configuration matrix.

Three independent sources of truth are collected per (kernel, config):

  1. what the compiler says   -- optimisation records (-fsave-optimization-record)
  2. what the binary contains -- vector register usage in the disassembled loop
  3. what the hardware did    -- wall time percentiles from the in-process harness

(2) exists because (1) can be misleading: a Passed record for the loop does not
guarantee the hot body ended up with vector instructions after later passes.
Disagreement between (1) and (2) is itself a finding, so it is recorded rather
than resolved.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KERNELS = ROOT / "kernels"
INCLUDE = ROOT / "include"
RESULTS = ROOT / "results"

# The hot loop always lives in a function called `body` in every kernel, so the
# optimisation records and the disassembly can both be filtered to it. Without
# that filter the records are dominated by setup and main, which vectorise
# incidentally and tell us nothing.
HOT_FN = "body"

CONFIGS: dict[str, list[str]] = {
    # Baseline optimisation, vectoriser on but conservative cost model.
    "O2":            ["-O2"],
    # Default aggressive optimisation for a generic target.
    "O3":            ["-O3"],
    # Same, but the cost model now knows the real vector width of this machine.
    "O3_native":     ["-O3", "-march=native"],
    # Scalar control. Every speedup in the results is measured against this.
    "O3_novec":      ["-O3", "-march=native", "-fno-vectorize", "-fno-slp-vectorize"],
    # Allows FP reassociation, which is what a float reduction needs.
    "O3_native_ffm": ["-O3", "-march=native", "-ffast-math"],
    # Forces the vectoriser past its own cost model, so we can measure what the
    # cost model avoided. Where this is faster than O3_native the model was wrong.
    "O3_native_force": ["-O3", "-march=native", "-mllvm", "-force-vector-width=8"],
}

BASELINE = "O3_novec"

# --------------------------------------------------------------------------- #
# optimisation record parsing
# --------------------------------------------------------------------------- #

# The record format uses YAML custom tags (!Passed, !Missed, !Analysis) and the
# standard library has no YAML parser, so records are split and field-extracted
# directly. This is deliberately literal: a malformed record should produce an
# obviously empty row rather than a plausible wrong one.
_REC = re.compile(r"^--- !(\w+)\s*$", re.M)


@dataclass
class Remark:
    kind: str = ""          # Passed | Missed | Analysis
    name: str = ""          # Vectorized | MissedDetails | CantVectorize... etc
    function: str = ""
    line: str = ""
    vf: str = ""            # vectorisation factor
    interleave: str = ""
    text: str = ""          # flattened human-readable message


def parse_opt_records(path: Path, function: str) -> list[Remark]:
    if not path.exists():
        return []
    raw = path.read_text(errors="replace")
    out: list[Remark] = []
    marks = list(_REC.finditer(raw))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        chunk = raw[m.end():end]
        if "loop-vectorize" not in chunk:
            continue
        fn = _field(chunk, "Function")
        if fn != function:
            continue
        strings = re.findall(r"String:\s+'([^']*)'", chunk)
        out.append(
            Remark(
                kind=m.group(1),
                name=_field(chunk, "Name"),
                function=fn,
                line=_field(chunk, "Line").rstrip(","),
                vf=_field(chunk, "VectorizationFactor").strip("'"),
                interleave=_field(chunk, "InterleaveCount").strip("'"),
                text="".join(strings).strip(),
            )
        )
    return out


def _field(chunk: str, key: str) -> str:
    m = re.search(rf"{key}:\s*(.+)", chunk)
    return m.group(1).strip().strip("'") if m else ""


# --------------------------------------------------------------------------- #
# binary inspection
# --------------------------------------------------------------------------- #

_YMM = re.compile(r"%ymm\d+")
_ZMM = re.compile(r"%zmm\d+")
_XMM = re.compile(r"%xmm\d+")

# On x86-64 scalar floating point also uses xmm registers, so counting register
# references alone reports the scalar control as "vectorised". Packed operation
# mnemonics are the reliable signal: the ss/sd suffix means scalar single or
# scalar double, ps/pd means packed. Integer SIMD is matched separately since it
# carries no such suffix.
_PACKED_FP = re.compile(r"\b v?(?:add|sub|mul|div|max|min|sqrt|fmadd\d*|fmsub\d*|"
                        r"and|or|xor|cmp|cvt\w*)[ps][sd]\b", re.X)
_SCALAR_FP = re.compile(r"\b v?(?:add|sub|mul|div|max|min|sqrt|cmp)s[sd]\b", re.X)
_PACKED_INT = re.compile(r"\b v?p(?:add|sub|mull|maddwd|minsw|maxsw|acksswb|and|or|xor|"
                         r"cmpeq|srl|sll|sra|movzx|shufb|broadcast)\w*\b", re.X)
_MOV_PACKED = re.compile(r"\b v?mov(?:aps|ups|apd|upd|dqa|dqu)\b")

def disassemble_fn(binary: Path, function: str) -> str:
    """Disassembly of one function, or empty string if it cannot be isolated."""
    try:
        txt = subprocess.run(
            ["objdump", "-d", "--no-show-raw-insn", str(binary)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    # Function blocks look like: "0000000000001234 <body>:" up to a blank line.
    m = re.search(rf"^[0-9a-f]+ <{re.escape(function)}>:\n(.*?)(?:\n\n|\Z)",
                  txt, re.M | re.S)
    return m.group(1) if m else ""


def vector_profile(asm: str) -> dict[str, int]:
    """Classify the disassembled loop body.

    `packed_ops` is the figure that decides whether the loop really vectorised.
    `scalar_fp_ops` is kept alongside it because a partially vectorised loop
    with a scalar remainder is a distinct and common outcome.
    """
    packed = (len(_PACKED_FP.findall(asm))
              - len(_SCALAR_FP.findall(asm))      # ss/sd also match the FP pattern
              + len(_PACKED_INT.findall(asm))
              + len(_MOV_PACKED.findall(asm)))
    return {
        "zmm_refs": len(_ZMM.findall(asm)),
        "ymm_refs": len(_YMM.findall(asm)),
        "xmm_refs": len(_XMM.findall(asm)),
        "packed_ops": max(packed, 0),
        "scalar_fp_ops": len(_SCALAR_FP.findall(asm)),
        "insn_count": sum(1 for ln in asm.splitlines() if "\t" in ln),
    }


# --------------------------------------------------------------------------- #
# build and run
# --------------------------------------------------------------------------- #

@dataclass
class Row:
    kernel: str = ""
    config: str = ""
    flags: str = ""
    compiled: int = 0
    # compiler claim
    vectorized_claim: int = 0
    vf: str = ""
    interleave: str = ""
    remark_kind: str = ""
    remark_name: str = ""
    remark_text: str = ""
    # binary evidence
    zmm_refs: int = 0
    ymm_refs: int = 0
    xmm_refs: int = 0
    packed_ops: int = 0
    scalar_fp_ops: int = 0
    insn_count: int = 0
    widest_vector: str = "scalar"
    # measurement
    n: int = 0
    reps: int = 0
    p50_s: float = 0.0
    p99_s: float = 0.0
    min_s: float = 0.0
    sd_s: float = 0.0
    rsd_pct: float = 0.0
    checksum: str = ""
    # metadata
    property: str = ""
    flops_per_elem: float = 0.0
    bytes_per_elem: float = 0.0
    governor: str = ""
    pin_failed: int = 0


def build_and_measure(src: Path, cfg: str, flags: list[str], cc: str,
                      n: int, reps: int, warm: int, cpu: int,
                      keep: Path | None) -> Row:
    row = Row(kernel=src.stem, config=cfg, flags=" ".join(flags))
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        binary = td / src.stem
        cmd = [cc, *flags, "-fsave-optimization-record",
               f"-foptimization-record-file={td / 'rec.opt.yaml'}",
               "-D_GNU_SOURCE", f"-I{INCLUDE}", "-o", str(binary), str(src), "-lm"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            row.remark_text = f"compile failed: {proc.stderr.strip().splitlines()[:1]}"
            return row
        row.compiled = 1

        # 1. compiler claim, restricted to the hot function
        remarks = parse_opt_records(td / "rec.opt.yaml", HOT_FN)
        passed = [r for r in remarks if r.kind == "Passed" and r.name == "Vectorized"]
        if passed:
            r = passed[0]
            row.vectorized_claim, row.vf, row.interleave = 1, r.vf, r.interleave
            row.remark_kind, row.remark_name, row.remark_text = r.kind, r.name, r.text
        else:
            # Prefer the Analysis record: it names the actual blocking reason,
            # whereas Missed records are often a generic restatement.
            pick = next((r for r in remarks if r.kind == "Analysis"), None) \
                or next((r for r in remarks if r.kind == "Missed"), None)
            if pick:
                row.remark_kind, row.remark_name, row.remark_text = \
                    pick.kind, pick.name, pick.text

        # 2. binary evidence
        prof = vector_profile(disassemble_fn(binary, HOT_FN))
        for k, v in prof.items():
            setattr(row, k, v)
        # A register reference is not evidence of vectorisation; a packed
        # operation is. Width is only reported once packed ops are present.
        if prof["packed_ops"] == 0:
            row.widest_vector = "scalar"
        elif prof["zmm_refs"]:
            row.widest_vector = "zmm"
        elif prof["ymm_refs"]:
            row.widest_vector = "ymm"
        else:
            row.widest_vector = "xmm"

        if keep:
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copy(td / "rec.opt.yaml", keep / f"{src.stem}.{cfg}.opt.yaml")

        # 3. measurement
        run = subprocess.run([str(binary), str(n), str(reps), str(warm), str(cpu)],
                             capture_output=True, text=True)
        if run.returncode != 0:
            row.remark_text = (row.remark_text + " | run failed").strip(" |")
            return row
        kv = dict(ln.split("=", 1) for ln in run.stdout.splitlines() if "=" in ln)
        row.n = int(kv.get("n", 0))
        row.reps = int(kv.get("reps", 0))
        row.p50_s = float(kv.get("p50_s", 0))
        row.p99_s = float(kv.get("p99_s", 0))
        row.min_s = float(kv.get("min_s", 0))
        row.sd_s = float(kv.get("sd_s", 0))
        row.rsd_pct = float(kv.get("rsd_pct", 0))
        row.checksum = kv.get("checksum", "")
        row.property = kv.get("property", "")
        row.flops_per_elem = float(kv.get("flops_per_elem", 0))
        row.bytes_per_elem = float(kv.get("bytes_per_elem", 0))
        for ln in run.stderr.splitlines():
            if ln.startswith("env.governor="):
                row.governor = ln.split("=", 1)[1]
            if ln.startswith("warn.pin_failed="):
                row.pin_failed = 1
    return row


def environment(cc: str) -> dict:
    def cap(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return "unavailable"
    model = ""
    try:
        for ln in Path("/proc/cpuinfo").read_text().splitlines():
            if ln.startswith("model name"):
                model = ln.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "compiler": cap([cc, "--version"]).splitlines()[0] if cap([cc, "--version"]) else "",
        "cpu_model": model,
        "cpu_count": os.cpu_count(),
        "kernel": platform.release(),
        "platform": platform.platform(),
        "perf_available": bool(shutil.which("perf")),
        "objdump_available": bool(shutil.which("objdump")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cc", default="clang")
    ap.add_argument("-n", type=int, default=1 << 22, help="elements per kernel")
    ap.add_argument("--reps", type=int, default=51)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--cpu", type=int, default=0, help="core to pin to")
    ap.add_argument("--only", default="", help="substring filter on kernel name")
    ap.add_argument("--keep-records", action="store_true",
                    help="archive raw optimisation records under results/records")
    ap.add_argument("--out", default=str(RESULTS / "raw.csv"))
    args = ap.parse_args()

    srcs = sorted(p for p in KERNELS.glob("k*.c") if args.only in p.stem)
    if not srcs:
        print("no kernels matched", file=sys.stderr)
        return 1

    RESULTS.mkdir(parents=True, exist_ok=True)
    keep = (RESULTS / "records") if args.keep_records else None

    env = environment(args.cc)
    (RESULTS / "environment.json").write_text(json.dumps(env, indent=2))
    print(json.dumps(env, indent=2), file=sys.stderr)
    if not env["perf_available"]:
        print("note: perf not present, hardware counters are omitted from this run",
              file=sys.stderr)

    rows: list[Row] = []
    for src in srcs:
        for cfg, flags in CONFIGS.items():
            row = build_and_measure(src, cfg, flags, args.cc,
                                    args.n, args.reps, args.warmup, args.cpu, keep)
            rows.append(row)
            print(f"{row.kernel:<22} {cfg:<17} "
                  f"claim={'Y' if row.vectorized_claim else 'n'} "
                  f"vf={row.vf or '-':<2} asm={row.widest_vector:<6} "
                  f"p50={row.p50_s*1e3:8.4f}ms rsd={row.rsd_pct:5.2f}%",
                  file=sys.stderr)

    out = Path(args.out)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))
    print(f"\nwrote {out} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
