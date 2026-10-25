"""Feasibility checks for a CVRP solution. Used by tools/validate.py and the solver."""

from cvrp.io import route_cost


def validate(demands, dist, capacity, vehicles, routes, printed_cost=None, cost_tol=0.01):
    """Return (errors, cost). errors is empty when the solution is feasible.

    cost is recomputed from the matrix over all well-formed routes.
    If printed_cost is given, it must match the recomputed cost within cost_tol
    (absolute) to allow for rounding when printing.
    """
    errors = []
    n = len(demands) - 1
    visits = [0] * (n + 1)
    cost = 0.0
    used = 0

    for k in range(len(routes)):
        route = routes[k]
        label = "route %d" % (k + 1)
        if len(route) < 2 or route[0] != 0 or route[-1] != 0:
            errors.append(label + " does not start and end at 0")
            continue
        if len(route) == 2:
            continue  # empty route 0 0 is ignored
        used += 1
        load = 0
        well_formed = True
        for v in route[1:-1]:
            if v == 0:
                errors.append(label + " visits the depot in the middle")
            elif v < 1 or v > n:
                errors.append(label + " has unknown vertex %d" % v)
                well_formed = False
            else:
                visits[v] += 1
                load += demands[v]
        if load > capacity:
            errors.append(label + " load %s exceeds capacity %s" % (load, capacity))
        if well_formed:
            cost += route_cost(route, dist)

    missing = [i for i in range(1, n + 1) if visits[i] == 0]
    repeated = [i for i in range(1, n + 1) if visits[i] > 1]
    if missing:
        errors.append("%d customers not visited, e.g. %s" % (len(missing), missing[:10]))
    if repeated:
        errors.append("%d customers visited more than once, e.g. %s" % (len(repeated), repeated[:10]))
    if used > vehicles:
        errors.append("%d routes used but only %d vehicles" % (used, vehicles))
    if printed_cost is not None and abs(printed_cost - cost) > cost_tol:
        errors.append("printed cost %s does not match recomputed cost %.4f" % (printed_cost, cost))
    return errors, cost
