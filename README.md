# CS602 Group Project: CVRP Solver

Solver and instance generator for the Capacitated Vehicle Routing Problem (CS602, SMU, AY2026/27).

## Requirements

- Python 3.9 or newer. Tested with Python 3.12.10.
- Standard library only. `requirements.txt` is empty, so the install step does nothing but is safe to run.

## Install

```
pip install -r requirements.txt
```

## Run

From the repository root:

```
python solver/solver.py <instance_file> --time-limit <L> > solution.txt
```

| Instance size | L (seconds) | Our solver stops at about |
|---------------|-------------|---------------------------|
| Small         | 30          | 25.5 s                    |
| Medium        | 60          | 51 s                      |
| Large         | 180         | 153 s                     |

- The solver keeps improving its answer until 85% of L, then prints the best feasible solution.
  The clock starts when the program starts, so file reading is included.
- If `--time-limit` is not given, it assumes 30 seconds (the safe choice, since the size class
  cannot be read from the file).
- Optional: `--seed N` (default 0). The same seed and time limit give the same search path.
- Only the solution goes to stdout. Progress messages go to stderr.

Output format: total cost on the first line, then one route per line, each starting and ending at 0.

## Generate instances

```
python generator/gen.py --n 200 --seed 1 --out instances/medium/m_200_1.txt
python generator/gen.py --n 800 --seed 7 --type clustered --depot corner --slack 1.0 --out instances/large/l_cl_800_7.txt
```

Options: `--type uniform|clustered|mixed`, `--depot center|corner|random`, `--clusters K`,
`--demand-max`, `--route-size` (average customers per truck), `--slack` (vehicles = First-Fit-Decreasing
truck count x slack). The same arguments and seed always produce the identical file.

## Submitted instances

`instances/manifest.csv` lists every generated instance with its seed and the exact command that
reproduces it. The example from the project specification is in `tests/data/spec_example.txt` (test only, not submitted).

## Tools

```
python tools/validate.py <instance> <solution>          # PASS/FAIL with reasons
python tools/batch_run.py instances/medium --time-limit 60 --out results/run.csv
python tools/score.py results/run.csv                   # official scoring formula
python tools/convert_cvrplib.py <file.vrp> --out-dir instances/benchmark
```

## Method

1. Construction: Clarke-Wright savings (and Nearest Neighbor), with repair if there are too many routes.
   For tight fleets: route elimination, then a packing-based fallback.
2. Local search with relocate, Or-opt, swap, 2-opt and 2-opt* moves, delta evaluation and
   nearest-neighbour candidate lists.
3. Adaptive Large Neighbourhood Search (random, worst, string and route removal, greedy and regret
   insertion, simulated annealing acceptance) until the time budget is used.
4. Every solution is validated before it is kept. Only a feasible solution is printed.
