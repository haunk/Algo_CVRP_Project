"""Convert CVRPLIB instances (.vrp, EUC_2D) into our instance format, for benchmarking.

Usage:
  python tools/convert_cvrplib.py <file.vrp> [<file.vrp> ...] --out-dir instances/benchmark

For every X.vrp, a matching X.sol next to it (if present) gives the best known cost and its
number of routes, which becomes our `Vehicles:` value. Without a .sol file the vehicle count is
taken from the "-k<number>" part of the name (the minimum number of routes).
Distances follow the CVRPLIB convention: Euclidean distance rounded to the nearest integer.
Best known costs are appended to <out-dir>/bks.csv (file, n, vehicles, bks).

Source used for the files: https://github.com/PyVRP/Instances (folder CVRP).
"""
import argparse
import csv
import math
import os
import re


def read_vrp(path):
    with open(path) as f:
        lines = [line.strip() for line in f]
    capacity = None
    coords = {}
    demand = {}
    depot = None
    section = None
    for line in lines:
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("CAPACITY"):
            capacity = int(line.split(":")[1])
        elif upper.startswith("EDGE_WEIGHT_TYPE") and "EUC_2D" not in upper:
            raise ValueError("only EUC_2D instances are supported")
        elif upper.startswith("NODE_COORD_SECTION"):
            section = "coord"
        elif upper.startswith("DEMAND_SECTION"):
            section = "demand"
        elif upper.startswith("DEPOT_SECTION"):
            section = "depot"
        elif upper.startswith("EOF"):
            break
        elif section == "coord":
            k, x, y = line.split()
            coords[int(k)] = (float(x), float(y))
        elif section == "demand":
            k, q = line.split()
            demand[int(k)] = int(q)
        elif section == "depot":
            k = int(line.split()[0])
            if k > 0 and depot is None:
                depot = k
    # Our format puts the depot at index 0, then the customers in file order
    order = [depot] + [k for k in sorted(coords) if k != depot]
    points = [coords[k] for k in order]
    demands = [0] + [demand[k] for k in order[1:]]
    return points, demands, capacity


def read_sol(path):
    routes = 0
    cost = None
    with open(path) as f:
        for line in f:
            if line.lower().startswith("route"):
                routes += 1
            elif line.lower().startswith("cost"):
                cost = float(line.split()[1])
    return routes, cost


def main():
    p = argparse.ArgumentParser(description="Convert CVRPLIB .vrp files to our format.")
    p.add_argument("files", nargs="+")
    p.add_argument("--out-dir", default="instances/benchmark")
    args = p.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    bks_path = os.path.join(args.out_dir, "bks.csv")
    new_file = not os.path.exists(bks_path)
    with open(bks_path, "a", newline="") as bks_file:
        writer = csv.writer(bks_file)
        if new_file:
            writer.writerow(["file", "n", "vehicles", "bks"])
        for path in args.files:
            points, demands, capacity = read_vrp(path)
            name = os.path.splitext(os.path.basename(path))[0]
            sol_path = os.path.splitext(path)[0] + ".sol"
            bks = ""
            if os.path.exists(sol_path):
                vehicles, cost = read_sol(sol_path)
                bks = "%g" % cost
            else:
                vehicles = int(re.search(r"-k(\d+)", name).group(1))

            lines = [" ".join(str(q) for q in demands)]
            for a in points:
                lines.append(" ".join(str(int(math.floor(math.hypot(a[0] - b[0], a[1] - b[1]) + 0.5)))
                                      for b in points))
            lines.append("Capacity: %d" % capacity)
            lines.append("Vehicles: %d" % vehicles)
            out = os.path.join(args.out_dir, name + ".txt")
            with open(out, "w", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            writer.writerow([name + ".txt", len(demands) - 1, vehicles, bks])
            print("wrote %s  n=%d  vehicles=%d  bks=%s" % (out, len(demands) - 1, vehicles, bks))


if __name__ == "__main__":
    main()
