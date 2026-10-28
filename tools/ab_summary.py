"""Summarise a folder written by run_ab.sh: mean cost change of each version against a base version.

Usage (from the repo root): python tools/ab_summary.py <folder> <base version>
Costs are averaged over seeds per instance, then the percentage changes are averaged over instances.
"""
import csv
import glob
import os
import sys

LIMITS = {"small": 30, "medium": 60, "large": 180}

folder, base = sys.argv[1], sys.argv[2]
rows = []
for path in glob.glob(os.path.join(folder, "*.csv")):
    with open(path) as f:
        rows.extend(csv.DictReader(f))

cost = {}       # (version, instance) -> costs over seeds
problems = 0
max_time = {}
for r in rows:
    version = r["version"].rsplit("_s", 1)[0]
    cost.setdefault((version, r["instance"]), []).append(float(r["cost"]))
    ratio = float(r["time"]) / LIMITS[r["size"]]
    problems += r["feasible"] != "1" or ratio > 1
    max_time[version] = max(max_time.get(version, 0), ratio)

others = sorted({v for v, _ in cost} - {base})
instances = sorted({i for _, i in cost})
print("%-18s %14s" % ("instance", base + " (mean)") + "".join(" %10s" % v for v in others))
changes = {v: [] for v in others}
for inst in instances:
    b = cost.get((base, inst))
    if not b:
        continue
    b = sum(b) / len(b)
    line = "%-18s %14.1f" % (inst, b)
    for v in others:
        c = cost.get((v, inst))
        if c:
            change = 100 * (sum(c) / len(c) - b) / b
            changes[v].append(change)
            line += " %+9.2f%%" % change
        else:
            line += " %10s" % "-"
    print(line)
for v in others:
    if changes[v]:
        print("mean change %-10s %+.3f%% over %d instances" % (v, sum(changes[v]) / len(changes[v]), len(changes[v])))
print("runs: %d, infeasible or over L: %d" % (len(rows), problems))
print("largest time / L: " + ", ".join("%s %.3f" % kv for kv in sorted(max_time.items())))
