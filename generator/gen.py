"""CVRP instance generator.

Usage: python generator/gen.py --n 50 --seed 1 --out instances/small/s_50_1.txt
       python generator/gen.py --n 800 --seed 7 --type clustered --depot corner --slack 1.0
                               --out instances/large/l_cl_800_7.txt

Points lie in a 1000 x 1000 square. Layout types:
  uniform    customers spread evenly over the square
  clustered  customers scattered (Gaussian) around a few random centres
  mixed      half uniform, half clustered
Depot position: centre, corner (0, 0) or a random point.

The same arguments and seed always produce the identical file. Each generated file is also
recorded in instances/manifest.csv (file, settings, capacity, vehicles and the exact command),
so the submitted instances can be reproduced. Use --no-manifest for throw-away files.

Feasibility is guaranteed: no demand exceeds the capacity, and the vehicle count is at least
the number of trucks First-Fit-Decreasing bin packing needs.
"""
import argparse
import csv
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "instances", "manifest.csv")
MANIFEST_FIELDS = ["file", "n", "type", "depot", "seed", "demand_max", "route_size", "slack",
                   "capacity", "vehicles", "command"]


def first_fit_decreasing(demands, capacity):
    """Number of trucks needed when packing demands largest first. Guarantees a feasible fleet size."""
    bins = []  # remaining space in each truck
    for q in sorted(demands, reverse=True):
        for b in range(len(bins)):
            if bins[b] >= q:
                bins[b] -= q
                break
        else:
            bins.append(capacity - q)
    return len(bins)


def _clustered_points(rng, count, clusters):
    """`count` points scattered around `clusters` random centres, clipped to the square."""
    centres = [(rng.uniform(100, 900), rng.uniform(100, 900)) for _ in range(clusters)]
    spread = 1000.0 / (4 * math.sqrt(clusters))  # smaller clusters when there are more of them
    points = []
    for _ in range(count):
        cx, cy = centres[rng.randrange(clusters)]
        x = min(1000.0, max(0.0, rng.gauss(cx, spread)))
        y = min(1000.0, max(0.0, rng.gauss(cy, spread)))
        points.append((x, y))
    return points


def generate(n, seed, demand_max, route_size, slack, layout="uniform", depot="center", clusters=0):
    rng = random.Random(seed)

    # 1. Points. The default (uniform, centre) draws random numbers in the same order as the
    #    first version of this generator, so older instances are reproduced exactly.
    if depot == "center":
        points = [(500.0, 500.0)]
    elif depot == "corner":
        points = [(0.0, 0.0)]
    else:
        points = [(rng.uniform(0, 1000), rng.uniform(0, 1000))]
    if clusters <= 0:
        clusters = max(3, n // 40)
    if layout == "uniform":
        for _ in range(n):
            points.append((rng.uniform(0, 1000), rng.uniform(0, 1000)))
    elif layout == "clustered":
        points += _clustered_points(rng, n, clusters)
    else:  # mixed
        half = n // 2
        for _ in range(n - half):
            points.append((rng.uniform(0, 1000), rng.uniform(0, 1000)))
        points += _clustered_points(rng, half, clusters)

    # 2. Demands: depot 0, customers 1..demand_max
    demands = [0] + [rng.randint(1, demand_max) for _ in range(n)]

    # 3. Distance matrix: Euclidean, rounded to 1 decimal, symmetric with 0 diagonal
    size = n + 1
    dist = [[0.0] * size for _ in range(size)]
    for i in range(size):
        for j in range(i + 1, size):
            d = round(math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]), 1)
            dist[i][j] = d
            dist[j][i] = d

    # 4. Capacity: about route_size customers per truck, never below the largest demand
    avg_demand = sum(demands) / n
    capacity = max(max(demands), int(round(avg_demand * route_size)))

    # 5. Vehicles: bin-packing count (always feasible) times slack
    min_vehicles = first_fit_decreasing(demands[1:], capacity)
    vehicles = int(math.ceil(min_vehicles * slack))

    return demands, dist, capacity, vehicles


def write_instance(path, demands, dist, capacity, vehicles):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    lines = [" ".join(str(q) for q in demands)]
    for row in dist:
        lines.append(" ".join("%.1f" % d for d in row))
    lines.append("Capacity: %d" % capacity)
    lines.append("Vehicles: %d" % vehicles)
    # newline="\n" keeps files identical on Windows and Linux
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def record(args, capacity, vehicles):
    """Add (or replace) this file's row in instances/manifest.csv."""
    rel = os.path.relpath(os.path.abspath(args.out), ROOT).replace(os.sep, "/")
    command = "python generator/gen.py --n %d --seed %d --type %s --depot %s --demand-max %d " \
              "--route-size %g --slack %g%s --out %s" % (
                  args.n, args.seed, args.type, args.depot, args.demand_max, args.route_size,
                  args.slack, " --clusters %d" % args.clusters if args.clusters else "", rel)
    row = {"file": rel, "n": args.n, "type": args.type, "depot": args.depot, "seed": args.seed,
           "demand_max": args.demand_max, "route_size": "%g" % args.route_size,
           "slack": "%g" % args.slack, "capacity": capacity, "vehicles": vehicles, "command": command}
    rows = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST, newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["file"] != rel]
    rows.append(row)
    rows.sort(key=lambda r: r["file"])
    with open(MANIFEST, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate a random CVRP instance.")
    parser.add_argument("--n", type=int, required=True, help="number of customers")
    parser.add_argument("--seed", type=int, required=True, help="random seed")
    parser.add_argument("--out", required=True, help="output file path")
    parser.add_argument("--type", choices=["uniform", "clustered", "mixed"], default="uniform",
                        help="customer layout (default uniform)")
    parser.add_argument("--depot", choices=["center", "corner", "random"], default="center",
                        help="depot position (default center)")
    parser.add_argument("--clusters", type=int, default=0,
                        help="number of clusters for clustered/mixed (default max(3, n/40))")
    parser.add_argument("--demand-max", type=int, default=10, help="max customer demand (default 10)")
    parser.add_argument("--route-size", type=float, default=10, help="avg customers per truck (default 10)")
    parser.add_argument("--slack", type=float, default=1.2, help="vehicles = bin-packing count x slack (default 1.2)")
    parser.add_argument("--no-manifest", action="store_true", help="do not record the file in instances/manifest.csv")
    args = parser.parse_args()

    demands, dist, capacity, vehicles = generate(args.n, args.seed, args.demand_max, args.route_size,
                                                 args.slack, args.type, args.depot, args.clusters)
    write_instance(args.out, demands, dist, capacity, vehicles)
    if not args.no_manifest:
        record(args, capacity, vehicles)
    print("wrote %s  n=%d  capacity=%d  vehicles=%d" % (args.out, args.n, capacity, vehicles))


if __name__ == "__main__":
    main()
