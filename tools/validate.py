"""Check a solution file against an instance file.

Usage: python tools/validate.py <instance_file> <solution_file>
Prints PASS or FAIL with reasons. Exit code 0 on PASS, 1 on FAIL.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvrp.io import read_instance, read_solution  # noqa: E402
from cvrp.validator import validate  # noqa: E402


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    demands, dist, capacity, vehicles = read_instance(argv[1])
    try:
        printed_cost, routes = read_solution(argv[2])
    except (OSError, ValueError) as e:
        print("FAIL")
        print("  cannot read solution: %s" % e)
        return 1

    errors, cost = validate(demands, dist, capacity, vehicles, routes, printed_cost)
    if errors:
        print("FAIL")
        for e in errors:
            print("  " + e)
        return 1
    used = sum(1 for r in routes if len(r) > 2)
    print("PASS cost=%.4f routes=%d/%d" % (cost, used, vehicles))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
