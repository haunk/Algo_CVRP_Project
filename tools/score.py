"""Apply the official scoring formula to a results CSV.

Usage: python tools/score.py <results.csv>

CSV columns: instance,size,version,time,cost,feasible
  size is small, medium or large. feasible is 1/0 or true/false.
For each instance, b is the best feasible cost among all rows of that instance.
"""
import csv
import sys

LIMIT = {"small": 30.0, "medium": 60.0, "large": 180.0}
WEIGHT = {"small": 0.1, "medium": 0.3, "large": 0.6}


def instance_score(t, limit, cost, best, feasible):
    if not feasible:
        return 0.0
    if t > 1.5 * limit:
        return 0.25
    return 1.0 / (0.5 * (2 ** max(0.0, t / limit - 1.0) + cost / best))


def main(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["time"] = float(r["time"])
        r["cost"] = float(r["cost"]) if r["cost"] else float("inf")
        r["feasible"] = str(r["feasible"]).strip().lower() in ("1", "true", "yes")

    best = {}
    for r in rows:
        if r["feasible"]:
            best[r["instance"]] = min(best.get(r["instance"], float("inf")), r["cost"])

    scores = {}  # version -> size -> list of scores
    for r in rows:
        feasible = r["feasible"] and r["instance"] in best
        b = best.get(r["instance"], 1.0)
        s = instance_score(r["time"], LIMIT[r["size"]], r["cost"], b, feasible)
        scores.setdefault(r["version"], {}).setdefault(r["size"], []).append(s)
        print("%-35s %-15s %.4f" % (r["instance"], r["version"], s))

    print()
    for version in scores:
        by_size = scores[version]
        parts = []
        weighted = 0.0
        weight_sum = 0.0
        for size in ("small", "medium", "large"):
            if size in by_size:
                avg = sum(by_size[size]) / len(by_size[size])
                parts.append("%s=%.4f" % (size, avg))
                weighted += WEIGHT[size] * avg
                weight_sum += WEIGHT[size]
        print("%-15s %s  final=%.4f" % (version, " ".join(parts), weighted / weight_sum))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
