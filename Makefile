# Defaults are deliberately modest so `make` finishes quickly. Grow N until no
# kernel is flagged cache_resident_suspect in results/verdicts.md.
# make predefines CC=cc, so a `?=` on CC never takes effect. Use our own name.
CLANG   ?= clang
N       ?= 2097152
REPS    ?= 31
WARMUP  ?= 5
CPU     ?= 0

.PHONY: all bench analyze clean docker check

all: bench analyze

bench:
	python3 runner.py --cc $(CLANG) -n $(N) --reps $(REPS) --warmup $(WARMUP) \
	                  --cpu $(CPU) --keep-records

analyze:
	python3 analyze.py --cc $(CLANG)

# Re-classify without re-measuring or re-calibrating.
reanalyze:
	python3 analyze.py --skip-calibration

# Sanity check: one kernel, few reps, verifies the toolchain end to end.
check:
	python3 runner.py --cc $(CLANG) --only k01 -n 1048576 --reps 11

docker:
	docker build -t llvm-vec-audit .
	docker run --rm -v "$$PWD/results:/work/results" llvm-vec-audit

clean:
	rm -rf results/*.csv results/*.json results/*.png results/*.md results/records
