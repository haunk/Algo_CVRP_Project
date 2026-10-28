"""Find how large an instance can be for each size class.

For every class (limit L), size n and scenario, generate an instance into instances/try/
(not recorded in the manifest), run the solver at L and at 3 x L, and log both costs.
An instance fits the class when the cost at L is within 0.5% of the cost at 3 x L.

Usage: python tools/size_sweep.py --out results/sweep.csv [--jobs 6]
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cvrp.io import read_instance  # noqa: E402
from cvrp.validator import validate  # noqa: E402

SCENARIOS = {
    "U": ["--type", "uniform", "--depot", "center"],
    "C": ["--type", "clustered", "--depot", "corner"],
    "T": ["--type", "mixed", "--depot", "random", "--slack", "1.0"],
}
CLASSES = {
    "small": (30, [200, 300, 400, 500]),
    "medium": (60, [400, 500, 600, 800]),
    "large": (180, [800, 1000, 1200, 1500]),
}
SEED_OFFSET = {"U": 1, "C": 2, "T": 3}


def instance_path(scenario, n):
    return os.path.join(ROOT, "instances", "try", "t_%s_%d.txt" % (scenario, n))


def generate(scenario, n):
    path = instance_path(scenario, n)
    if not os.path.exists(path):
        # The size word is not used here: solve() always passes --time-limit
        cmd = [sys.executable, os.path.join(ROOT, "generator", "gen.py"), "--size", "small", "--n", str(n),
               "--seed", str(n + SEED_OFFSET[scenario]), "--out", path, "--no-manifest"] + SCENARIOS[scenario]
        subprocess.run(cmd, check=True, capture_output=True)
    return path


def solve(path, limit):
    cmd = [sys.executable, os.path.join(ROOT, "solver", "solver.py"), path, "--time-limit", str(limit)]
    start = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5 * limit)
    elapsed = time.perf_counter() - start
    lines = [l.split() for l in proc.stdout.splitlines() if l.strip()]
    routes = [[int(t) for t in l] for l in lines[1:]]
    demands, dist, capacity, vehicles = read_instance(path)
    errors, cost = validate(demands, dist, capacity, vehicles, routes, float(lines[0][0]))
    return elapsed, cost, not errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--jobs", type=int, default=6)
    args = p.parse_args()

    jobs = []
    for size, (limit, ns) in CLASSES.items():
        for n in ns:
            for sc in SCENARIOS:
                generate(sc, n)
                for mult in (1, 3):
                    jobs.append((size, n, sc, mult, limit * mult))
    jobs.sort(key=lambda j: -j[4])  # longest runs first, so the pool finishes evenly

    new_file = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f, ThreadPoolExecutor(args.jobs) as pool:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["size", "n", "scenario", "limit", "time", "cost", "feasible"])
        futures = {pool.submit(solve, instance_path(sc, n), lim): (size, n, sc, lim)
                   for size, n, sc, mult, lim in jobs}
        for fut in as_completed(futures):
            size, n, sc, lim = futures[fut]
            elapsed, cost, ok = fut.result()
            writer.writerow([size, n, sc, lim, "%.2f" % elapsed, "%.4f" % cost, int(ok)])
            f.flush()
            print("%-6s n=%-5d %s L=%-4d t=%7.2f cost=%.2f feasible=%d" % (size, n, sc, lim, elapsed, cost, ok),
                  file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
