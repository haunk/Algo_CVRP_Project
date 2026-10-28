#!/bin/sh
# Compare solver versions on the 11 benchmarks (30 s) and our 9 instances (real limits), seeds 0 and 1.
# Each argument is NAME=COMMAND. One stream per (version, seed), all streams run in parallel.
# Usage (from the repo root):
#   sh tools/run_ab.sh results/speed "base=python /path/to/old/solver/solver.py" "speed=python solver/solver.py"
# Then: python tools/ab_summary.py results/speed base
out=$1; shift
mkdir -p "$out"
for spec in "$@"; do
  name=${spec%%=*}
  cmd=${spec#*=}
  for seed in 0 1; do
    (
      tag="${name}_s${seed}"
      python tools/batch_run.py instances/benchmark --size small --time-limit 30 --seed $seed \
        --version "$tag" --solver "$cmd" --out "$out/${tag}_bench.csv"
      for pair in small:30 medium:60 large:180; do
        python tools/batch_run.py instances/${pair%%:*} --time-limit ${pair#*:} --seed $seed \
          --version "$tag" --solver "$cmd" --out "$out/${tag}_${pair%%:*}.csv"
      done
    ) > "$out/${name}_s${seed}.log" 2>&1 &
  done
done
wait
echo done
