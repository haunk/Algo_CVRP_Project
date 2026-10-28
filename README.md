# CS602 Group Project: CVRP Solver

Solver and instance generator for the Capacitated Vehicle Routing Problem (CS602, SMU, AY2026/27).

## Requirements

- Python 3.9 or newer. Tested with Python 3.12.10.
- Standard library only. `requirements.txt` is empty, so the install step does nothing but is safe to run.

## Install

```
pip install -r requirements.txt
```

## Quick start

Run every command from the repository root (the folder that holds this README).

```
mkdir solutions
python solver/solver.py tests/data/spec_example.txt --time-limit 6 > solutions/spec.txt
python tools/validate.py tests/data/spec_example.txt solutions/spec.txt
```

Expected: `PASS cost=21.8000 routes=2/2`. This is the 3-customer example from the project
specification, and 21.8 is its optimal cost. It takes about 5 seconds.

The `solutions/` folder is ignored by git, so a fresh clone does not have it. `mkdir solutions` creates
it once.

## Run the solver

General form:

```
python solver/solver.py <instance_file> > <solution_file>
```

The time limit L comes from the first line of the instance file, which holds only the size class
`small`, `medium` or `large` (any capitalisation, as the instructor requires from all teams).
One example per size class, using our submitted instances:

```
python solver/solver.py instances/small/s_U_500.txt   > solutions/s_U_500.txt
python solver/solver.py instances/medium/m_U_800.txt  > solutions/m_U_800.txt
python solver/solver.py instances/large/l_U_1500.txt  > solutions/l_U_1500.txt
```

| Instance size | L (seconds) | Our solver stops at about |
|---------------|-------------|---------------------------|
| Small         | 30          | 25.5 s                    |
| Medium        | 60          | 51 s                      |
| Large         | 180         | 153 s                     |

- The solver keeps improving its answer until 85% of L, then prints the best feasible solution.
  The clock starts when the program starts, so file reading is included.
- `--time-limit L` overrides the size word. If the file has no size word and no `--time-limit` is
  given, the solver assumes 30 seconds (the safe choice).
- Optional: `--seed N` (default 0). The same seed and time limit give the same search path.
- Only the solution goes to stdout. Progress messages go to stderr, so you see them on screen while
  the solution goes to the file.

Output format: total cost on the first line, then one route per line, each starting and ending at 0.

```
21.8
0 1 0
0 2 3 0
```

Windows PowerShell 5.1 note: `>` writes the file as UTF-16. Our validator reads it, but other tools may
not. To get a plain text file, run the commands in Git Bash or cmd, or use
`| Out-File -Encoding ascii solutions/s_U_500.txt` instead of `> solutions/s_U_500.txt`.

## Check a solution

```
python tools/validate.py <instance_file> <solution_file>
```

Example:

```
python tools/validate.py instances/small/s_U_500.txt solutions/s_U_500.txt
```

It prints `PASS` with the recomputed cost, or `FAIL` with the reasons (missing customer, overloaded
route, too many routes, wrong printed cost).

## Run and score a whole folder

The batch runner solves every `.txt` file in a folder, validates each answer and appends one row per
instance to a CSV. The size class and time limit of each file come from its size word. Files without
it (for example the CVRPLIB benchmarks) need `--time-limit` and `--size`.

```
python tools/batch_run.py instances/small  --out results/run.csv
python tools/batch_run.py instances/medium --out results/run.csv
python tools/batch_run.py instances/large  --out results/run.csv
python tools/score.py results/run.csv
```

The three folders take about 1.5, 2.5 and 8 minutes. `score.py` applies the official formula. With only
one solver in the CSV, every score is 1.0, because our cost is also the best cost.

## Compare with another solver

Put the other solver in its own folder, for example `competitors/friend_a/solver.py` (ignored by git).
It must accept `<instance> --time-limit S --seed N` and print only the solution to stdout. Run both
solvers into the same CSV, each with its own `--version` name, then score:

```
python tools/batch_run.py instances/medium --version ours     --solver "python solver/solver.py"              --out results/compare.csv
python tools/batch_run.py instances/medium --version friend_a --solver "python competitors/friend_a/solver.py" --out results/compare.csv
python tools/score.py results/compare.csv
```

The batch runner always passes `--time-limit` to the solver it calls. For files without a size word,
add `--time-limit L --size small|medium|large` so the scorer uses the right limit.

## Generate instances

General form:

```
python generator/gen.py --size small|medium|large --n <customers> --seed <seed> --out <file> [options]
```

`--size` is written as the first line of the file. Distances are Euclidean in a 1000 x 1000 square,
rounded to 1 decimal, so every number has at most 5 significant digits (the limit is 6).

Options: `--type uniform|clustered|mixed`, `--depot center|corner|random`, `--clusters K`,
`--demand-max`, `--route-size` (average customers per truck), `--slack` (vehicles = First-Fit-Decreasing
truck count x slack, 1.0 gives the fewest trucks possible). The same arguments and seed always produce
the identical file.

Every generated file is recorded in `instances/manifest.csv`. For test files, write to `instances/try/`
(ignored by git) and add `--no-manifest`:

```
python generator/gen.py --size small --n 300 --seed 7 --type clustered --depot corner --out instances/try/t_C_300.txt --no-manifest
```

## Submitted instances

Three scenarios per size class: U (uniform customers, depot in the center), C (clustered customers,
depot in a corner) and T (tight fleet: mixed layout, random depot, fewest trucks possible).

| Class | Limit | File | Seed | Command |
|-------|-------|------|------|---------|
| Small | 30 s | `instances/small/s_U_500.txt` | 501 | `python generator/gen.py --size small --n 500 --seed 501 --type uniform --depot center --out instances/small/s_U_500.txt` |
| Small | 30 s | `instances/small/s_C_500.txt` | 502 | `python generator/gen.py --size small --n 500 --seed 502 --type clustered --depot corner --out instances/small/s_C_500.txt` |
| Small | 30 s | `instances/small/s_T_500.txt` | 503 | `python generator/gen.py --size small --n 500 --seed 503 --type mixed --depot random --slack 1.0 --out instances/small/s_T_500.txt` |
| Medium | 60 s | `instances/medium/m_U_800.txt` | 801 | `python generator/gen.py --size medium --n 800 --seed 801 --type uniform --depot center --out instances/medium/m_U_800.txt` |
| Medium | 60 s | `instances/medium/m_C_800.txt` | 802 | `python generator/gen.py --size medium --n 800 --seed 802 --type clustered --depot corner --out instances/medium/m_C_800.txt` |
| Medium | 60 s | `instances/medium/m_T_800.txt` | 803 | `python generator/gen.py --size medium --n 800 --seed 803 --type mixed --depot random --slack 1.0 --out instances/medium/m_T_800.txt` |
| Large | 180 s | `instances/large/l_U_1500.txt` | 1501 | `python generator/gen.py --size large --n 1500 --seed 1501 --type uniform --depot center --out instances/large/l_U_1500.txt` |
| Large | 180 s | `instances/large/l_C_1500.txt` | 1502 | `python generator/gen.py --size large --n 1500 --seed 1502 --type clustered --depot corner --out instances/large/l_C_1500.txt` |
| Large | 180 s | `instances/large/l_T_1500.txt` | 1503 | `python generator/gen.py --size large --n 1500 --seed 1503 --type mixed --depot random --slack 1.0 --out instances/large/l_T_1500.txt` |

`instances/manifest.csv` holds the same commands plus capacity and vehicle counts. The sizes come from
`tools/size_sweep.py` (results in `results/sweep.csv`): at these sizes, 3 times more time improves our
cost by less than 1%. The example from the project specification is in `tests/data/spec_example.txt`
(test only, not submitted).

To check that a submitted file reproduces exactly, regenerate it into `instances/try/` and compare:

```
python generator/gen.py --size small --n 500 --seed 501 --type uniform --depot center --out instances/try/check.txt --no-manifest
git diff --no-index --stat instances/small/s_U_500.txt instances/try/check.txt
```

No output from the second command means the files are identical.

## Folder layout

```
solver/solver.py      the solver (entry point)
cvrp/                 solver modules: reading files, construction, local search, ALNS, validation
generator/gen.py      instance generator
tools/                validate, batch_run, score, size_sweep, convert_cvrplib, run_compare, run_ab, ab_summary
instances/            small/ medium/ large/ (submitted), manifest.csv, benchmark/ (CVRPLIB X instances)
tests/data/           specification example and its known correct solution
results/              CSV logs of experiments (not in git, recreate them with the commands below)
report/figures/       figures for the report
```

## Other tools

```
python tools/size_sweep.py --out results/sweep.csv --jobs 6       # how large each size class can be (about 40 min)
python tools/convert_cvrplib.py <file.vrp> --out-dir instances/benchmark
python tools/batch_run.py instances/benchmark --size small --time-limit 30 --out results/bench.csv
```

`instances/benchmark/bks.csv` lists the best known cost of each benchmark instance, to measure how far
our cost is from it.

## Method

1. Construction: Clarke-Wright savings (and Nearest Neighbor), with repair if there are too many routes.
   For tight fleets: route elimination, then a packing-based fallback.
2. Local search with relocate, Or-opt, swap, 2-opt and 2-opt* moves, delta evaluation and
   nearest-neighbour candidate lists.
3. Adaptive Large Neighbourhood Search (random, worst, string and route removal, greedy and regret
   insertion, simulated annealing acceptance) until the time budget is used.
4. Every solution is validated before it is kept. Only a feasible solution is printed.

A diagram of this flow is in `report/figures/algorithm_flow.png`.
