#!/bin/sh
# Usage: sh results/run_compare.sh <version> "<solver command>"   e.g. algo1 "python solver/solver.py", algo2 "python competitors/Algo_2/solver.py"
V=$1; S=$2; OUT=results/compare_$V.csv
for spec in small:30 medium:60 large:180; do
  size=${spec%%:*}; L=${spec##*:}
  python tools/batch_run.py instances/$size            --size $size --time-limit $L --out $OUT --version $V --solver "$S"
  python tools/batch_run.py instances/compare/algo2_$size --size $size --time-limit $L --out $OUT --version $V --solver "$S"
done
