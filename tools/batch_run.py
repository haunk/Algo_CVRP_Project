"""Run a solver on every instance in a folder, validate, and append results to a CSV.

Usage:
  python tools/batch_run.py <folder> --out results/run.csv [--time-limit S]
                            [--size small|medium|large] [--version NAME]
                            [--solver "python solver/solver.py"] [--seed N]

Without --time-limit, each instance's limit comes from the size word on its first line
(small 30 s, medium 60 s, large 180 s). Files without the word are skipped.
The solver is called as: <solver> <instance> --time-limit S --seed N
and must print the solution to stdout. Wall-clock time includes process start-up.
The run is killed at 1.5 x time limit (the grader's hard cut-off).
"""
import argparse
import csv
import os
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cvrp.io import read_instance_with_size, TIME_LIMITS  # noqa: E402
from cvrp.validator import validate  # noqa: E402

FIELDS = ["instance", "size", "version", "seed", "time", "cost", "feasible", "routes", "vehicles", "note"]


def parse_output(text):
    lines = [l.split() for l in text.splitlines() if l.strip()]
    cost = float(lines[0][0])
    routes = [[int(t) for t in l] for l in lines[1:]]
    return cost, routes


def run_one(solver_cmd, path, time_limit, seed):
    cmd = solver_cmd + [path, "--time-limit", str(time_limit), "--seed", str(seed)]
    start = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5 * time_limit)
        elapsed = time.perf_counter() - start
        return elapsed, proc.stdout, proc.returncode, proc.stderr
    except subprocess.TimeoutExpired:
        return time.perf_counter() - start, "", None, "timeout"


def main():
    p = argparse.ArgumentParser(description="Batch-run a CVRP solver.")
    p.add_argument("folder")
    p.add_argument("--time-limit", type=float, default=None,
                   help="default: from the size word on each instance's first line")
    p.add_argument("--out", required=True)
    p.add_argument("--size", default=None, help="size label in the CSV (default: the size word, else the folder name)")
    p.add_argument("--version", default="dev")
    p.add_argument("--solver", default=None, help="solver command (default: this Python + solver/solver.py)")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    folder_size = os.path.basename(os.path.normpath(args.folder))
    if args.solver is None:
        # Build the default as a list: quoting the interpreter path breaks on Windows
        solver_cmd = [sys.executable, os.path.join(ROOT, "solver", "solver.py")]
    else:
        solver_cmd = shlex.split(args.solver, posix=(os.name != "nt"))
    files = sorted(f for f in os.listdir(args.folder) if f.endswith(".txt"))

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    new_file = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for name in files:
            path = os.path.join(args.folder, name)
            demands, dist, capacity, vehicles, size_class = read_instance_with_size(path)
            time_limit = args.time_limit
            if time_limit is None:
                if size_class is None:
                    print("%s: no size word on the first line, pass --time-limit" % name, file=sys.stderr)
                    continue
                time_limit = TIME_LIMITS[size_class]
            elapsed, stdout, code, stderr = run_one(solver_cmd, path, time_limit, args.seed)
            row = {"instance": name, "size": args.size or size_class or folder_size, "version": args.version, "seed": args.seed,
                   "time": "%.3f" % elapsed, "cost": "", "feasible": 0, "routes": "",
                   "vehicles": vehicles, "note": ""}
            if code is None:
                row["note"] = "timeout"
            else:
                try:
                    printed, routes = parse_output(stdout)
                    errors, cost = validate(demands, dist, capacity, vehicles, routes, printed)
                    row["cost"] = "%.4f" % cost
                    row["routes"] = sum(1 for r in routes if len(r) > 2)
                    row["feasible"] = 0 if errors else 1
                    row["note"] = "; ".join(errors)[:200]
                except (ValueError, IndexError):
                    row["note"] = "unreadable output (exit %s): %s" % (code, stderr.strip()[-150:])
            writer.writerow(row)
            f.flush()
            print("%-35s t=%7.2fs cost=%-12s feasible=%s %s" % (
                name, elapsed, row["cost"], row["feasible"], row["note"]), file=sys.stderr)


if __name__ == "__main__":
    main()
