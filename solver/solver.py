"""CVRP solver: Clarke-Wright start, local search, then ALNS until the time budget is used.

Usage: python solver/solver.py <instance_file> [--time-limit S] [--seed N] [--stop-fraction F]

The time limit L is --time-limit if given, else it follows the size word on the first line of the
instance (small 30 s, medium 60 s, large 180 s), else 30 s.
Prints the solution to stdout. Progress messages go to stderr.

Time is measured from program start (including imports and file reading). The search stops at
stop_fraction * time_limit, then the best solution is validated and printed.
"""
import time

START = time.perf_counter()  # first line on purpose: the clock includes everything below

import argparse  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cvrp.io import read_instance_with_size, format_solution, TIME_LIMITS  # noqa: E402
from cvrp.validator import validate  # noqa: E402
from cvrp.construct import (nearest_neighbors, nearest_neighbor, clarke_wright,  # noqa: E402
                            repair_vehicles, bin_packing_routes)
from cvrp.local_search import Solution, local_search  # noqa: E402
from cvrp.alns import alns  # noqa: E402
from cvrp.fleet import reduce_routes  # noqa: E402

# The size class (and so the time limit) of an instance is set by the group that made it, so the
# solver cannot tell it from n. Every file names its class on the first line. If neither that word
# nor --time-limit is there, we assume the smallest limit (30 s): finishing early only costs a
# little solution quality, while running late on a 30 s instance is very costly.
DEFAULT_TIME_LIMIT = 30.0
DEFAULT_STOP_FRACTION = 0.85
NEIGHBORS = 30             # size of the granular neighbour lists
FULL_SAVINGS_MAX_N = 800   # above this, Clarke-Wright uses neighbour pairs only


def log(msg):
    print("[%6.2fs] %s" % (time.perf_counter() - START, msg), file=sys.stderr)


def initial_solution(demands, dist, capacity, vehicles, neighbors):
    """Best feasible construction (Clarke-Wright or Nearest Neighbor plus simple repair), or None."""
    n = len(demands) - 1
    best = None
    best_cost = None
    cw_neighbors = neighbors if n > FULL_SAVINGS_MAX_N else None
    candidates = [
        ("clarke_wright", lambda: clarke_wright(demands, dist, capacity, cw_neighbors)),
        ("nearest_neighbor", lambda: nearest_neighbor(demands, dist, capacity)),
    ]
    for name, build in candidates:
        routes = build()
        if len(routes) > vehicles:
            repaired = repair_vehicles(routes, demands, dist, capacity, vehicles)
            log("%s: %d routes > %d vehicles, repair %s" % (
                name, len(routes), vehicles, "succeeded" if repaired else "failed"))
            if repaired is None:
                continue
            routes = repaired
        errors, cost = validate(demands, dist, capacity, vehicles, routes)
        log("%s: cost=%.2f routes=%d feasible=%s" % (name, cost, len(routes), not errors))
        if not errors and (best_cost is None or cost < best_cost):
            best, best_cost = routes, cost
        if n > FULL_SAVINGS_MAX_N:
            break  # nearest neighbour is O(n^2) and rarely better, skip it on large instances
    return best


def solve(demands, dist, capacity, vehicles, deadline, seed, keep):
    """Run the full pipeline. `keep(routes)` is called with every new best feasible solution."""
    rng = random.Random(seed)
    n = len(demands) - 1
    neighbors = nearest_neighbors(dist, NEIGHBORS)
    log("neighbour lists ready (k=%d)" % min(NEIGHBORS, max(n - 1, 0)))

    routes = initial_solution(demands, dist, capacity, vehicles, neighbors)

    if routes is None:
        # Tight fleet: eliminate routes from Clarke-Wright, using at most 25% of the remaining time
        cw = clarke_wright(demands, dist, capacity, neighbors if n > FULL_SAVINGS_MAX_N else None)
        sol = Solution.from_depot_routes(cw, demands, dist, capacity)
        limit = time.perf_counter() + 0.25 * (deadline - time.perf_counter())
        if reduce_routes(sol, neighbors, vehicles, limit, rng, log):
            routes = sol.to_routes()
        else:
            log("route elimination failed at %d routes" % sol.used_routes())

    if routes is None:
        routes = bin_packing_routes(demands, dist, capacity, vehicles, seed)
        log("bin packing fallback %s" % ("succeeded" if routes else "failed"))

    if routes is None:
        log("no feasible start found")
        return
    keep(routes)

    sol = Solution.from_depot_routes(routes, demands, dist, capacity)
    local_search(sol, neighbors, deadline, rng=rng)
    log("local search: cost=%.2f routes=%d" % (sol.cost(), sol.used_routes()))
    keep(sol.to_routes())

    best, iterations = alns(sol, neighbors, vehicles, deadline, rng, log)
    log("alns: %d iterations, cost=%.2f routes=%d" % (iterations, best.cost(), best.used_routes()))
    keep(best.to_routes())


def main():
    parser = argparse.ArgumentParser(description="CVRP solver (ALNS).")
    parser.add_argument("instance")
    parser.add_argument("--time-limit", type=float, default=None,
                        help="time limit L in seconds (default: from the size word on the first "
                             "line of the instance, else %g)" % DEFAULT_TIME_LIMIT)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--stop-fraction", type=float, default=DEFAULT_STOP_FRACTION,
                        help="stop searching at this fraction of the time limit (default %g)"
                             % DEFAULT_STOP_FRACTION)
    args = parser.parse_args()

    demands, dist, capacity, vehicles, size_class = read_instance_with_size(args.instance)
    if args.time_limit is not None:
        time_limit, source = args.time_limit, "--time-limit"
    elif size_class is not None:
        time_limit, source = TIME_LIMITS[size_class], "size word '%s'" % size_class
    else:
        time_limit, source = DEFAULT_TIME_LIMIT, "default"
    deadline = START + args.stop_fraction * time_limit
    log("read n=%d capacity=%s vehicles=%d, time limit %gs (%s)" % (
        len(demands) - 1, capacity, vehicles, time_limit, source))

    # Keep the best validated solution. Whatever goes wrong later, this is what gets printed.
    state = {"routes": None, "cost": None}

    def keep(routes):
        errors, cost = validate(demands, dist, capacity, vehicles, routes)
        if errors:
            log("rejected an infeasible solution: %s" % "; ".join(errors))
            return
        if state["cost"] is None or cost < state["cost"] - 1e-9:
            state["routes"], state["cost"] = routes, cost

    try:
        solve(demands, dist, capacity, vehicles, deadline, args.seed, keep)
    except Exception as e:  # safety net: still print the best solution found so far
        log("ERROR during search: %r" % (e,))

    if state["routes"] is None:
        # Nothing feasible was found. Print plain Clarke-Wright so there is at least an answer.
        log("WARNING: no feasible solution found, printing Clarke-Wright anyway")
        state["routes"] = clarke_wright(demands, dist, capacity)

    sys.stdout.write(format_solution(state["routes"], dist))
    log("done, cost=%.2f" % (state["cost"] if state["cost"] is not None else float("nan")))


if __name__ == "__main__":
    main()
