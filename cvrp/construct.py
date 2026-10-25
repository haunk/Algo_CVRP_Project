"""Construction heuristics: build a first solution quickly.

All functions take (demands, dist, capacity, ...) and return routes WITH depots,
for example [[0, 1, 0], [0, 2, 3, 0]], the same form the validator and writer use.
"""
import random


def nearest_neighbors(dist, k):
    """For every vertex, the k closest customers (never the depot, never itself)."""
    size = len(dist)
    k = min(k, size - 2)
    result = [[] for _ in range(size)]
    customers = list(range(1, size))
    for i in range(size):
        row = dist[i]
        order = sorted(customers, key=row.__getitem__)
        result[i] = [c for c in order if c != i][:k]
    return result


def nearest_neighbor(demands, dist, capacity):
    """Build routes: from the current stop, always go to the closest customer that still fits."""
    n = len(demands) - 1
    visited = [False] * (n + 1)
    routes = []
    remaining = n
    while remaining > 0:
        route = [0]
        load = 0
        current = 0
        while True:
            best = -1
            for c in range(1, n + 1):
                if not visited[c] and load + demands[c] <= capacity:
                    if best == -1 or dist[current][c] < dist[current][best]:
                        best = c
            if best == -1:
                break  # nothing else fits, return to depot
            route.append(best)
            visited[best] = True
            load += demands[best]
            current = best
            remaining -= 1
        route.append(0)
        routes.append(route)
    return routes


def clarke_wright(demands, dist, capacity, neighbors=None):
    """Savings method: start with one route per customer, then merge routes in order of savings.

    Merging the route ending at i with the route starting at j saves
    s(i, j) = d(0, i) + d(0, j) - d(i, j), because the trips i -> 0 and 0 -> j are replaced by i -> j.

    If `neighbors` is given (neighbors[i] = closest customers of i), only those pairs are
    considered. This keeps the savings list at n * k entries instead of n^2 / 2 for large n.
    """
    n = len(demands) - 1

    # 1. One route per customer: 0 -> i -> 0 (depots are added back at the end)
    route_of = list(range(n + 1))          # route_of[c] = id of the route containing customer c
    routes = {c: [c] for c in range(1, n + 1)}
    load = {c: demands[c] for c in range(1, n + 1)}

    # 2. Savings for every pair of customers (or every neighbour pair), largest first
    savings = []
    d0 = dist[0]
    for i in range(1, n + 1):
        row = dist[i]
        candidates = neighbors[i] if neighbors is not None else range(i + 1, n + 1)
        for j in candidates:
            if neighbors is not None and j < i and i in neighbors[j]:
                continue  # pair already added from j's list
            s = d0[i] + d0[j] - row[j]
            if s > 0:
                savings.append((s, i, j))
    savings.sort(reverse=True)

    # 3. Merge two routes when i and j are both route ends and the load fits
    for s, i, j in savings:
        ri = route_of[i]
        rj = route_of[j]
        if ri == rj:
            continue  # already in the same route
        a = routes[ri]
        b = routes[rj]
        if a[0] != i and a[-1] != i:
            continue  # i is in the middle of its route
        if b[0] != j and b[-1] != j:
            continue  # j is in the middle of its route
        if load[ri] + load[rj] > capacity:
            continue

        # Turn the routes around so that a ends with i and b starts with j
        if a[-1] != i:
            a.reverse()
        if b[0] != j:
            b.reverse()

        a.extend(b)
        load[ri] += load[rj]
        for c in b:
            route_of[c] = ri
        del routes[rj]
        del load[rj]

    return [[0] + r + [0] for r in routes.values()]


def repair_vehicles(routes, demands, dist, capacity, vehicles):
    """Reduce the number of routes to at most `vehicles`.

    While there are too many routes: remove the route with the smallest load and insert
    each of its customers (largest demand first) at the cheapest position in another
    route that still has room. Returns the repaired routes, or None if a customer
    cannot be placed anywhere. The input routes are not changed.
    """
    routes = [r[:] for r in routes]
    loads = [sum(demands[c] for c in r) for r in routes]

    while len(routes) > vehicles:
        # 1. Remove the route with the smallest load
        k = loads.index(min(loads))
        removed = routes.pop(k)
        loads.pop(k)
        customers = sorted(removed[1:-1], key=lambda c: demands[c], reverse=True)

        # 2. Insert each customer at its cheapest feasible position
        for c in customers:
            best_route = -1
            best_pos = -1
            best_delta = 0.0
            for r in range(len(routes)):
                if loads[r] + demands[c] > capacity:
                    continue  # no room in this truck
                route = routes[r]
                for p in range(1, len(route)):
                    a = route[p - 1]
                    b = route[p]
                    delta = dist[a][c] + dist[c][b] - dist[a][b]  # extra distance to visit c between a and b
                    if best_route == -1 or delta < best_delta:
                        best_route = r
                        best_pos = p
                        best_delta = delta
            if best_route == -1:
                return None  # customer c does not fit in any other truck
            routes[best_route].insert(best_pos, c)
            loads[best_route] += demands[c]

    return routes


def _first_fit(order, demands, capacity, vehicles):
    """Put customers into trucks in the given order, each into the first truck with room.

    Returns a list of groups (lists of customers), or None if more than `vehicles` trucks are needed.
    """
    groups = []
    space = []
    for c in order:
        for g in range(len(groups)):
            if space[g] >= demands[c]:
                groups[g].append(c)
                space[g] -= demands[c]
                break
        else:
            if len(groups) == vehicles:
                return None
            groups.append([c])
            space.append(capacity - demands[c])
    return groups


def packing_insertion(demands, dist, capacity, vehicles):
    """Largest demand first, each customer at its cheapest position in a route that has room.

    A new route is opened only when the customer fits nowhere and a vehicle is still free.
    Like First-Fit-Decreasing it packs big items first, but it also keeps routes compact.
    Returns routes with depots, or None if some customer could not be placed.
    """
    n = len(demands) - 1
    order = sorted(range(1, n + 1), key=lambda c: (-demands[c], dist[0][c]))
    routes = []
    loads = []
    for c in order:
        best = None  # (extra distance, route index, position)
        for r in range(len(routes)):
            if loads[r] + demands[c] > capacity:
                continue
            route = routes[r]
            for p in range(1, len(route)):
                delta = dist[route[p - 1]][c] + dist[c][route[p]] - dist[route[p - 1]][route[p]]
                if best is None or delta < best[0]:
                    best = (delta, r, p)
        if best is None:
            if len(routes) == vehicles:
                return None
            routes.append([0, c, 0])
            loads.append(demands[c])
        else:
            routes[best[1]].insert(best[2], c)
            loads[best[1]] += demands[c]
    return routes


def bin_packing_routes(demands, dist, capacity, vehicles, seed=0, attempts=200):
    """Fallback for very tight fleets: pack customers into trucks first, then order each truck.

    Tries the distance-aware packing_insertion first. If that needs too many trucks, tries
    First-Fit-Decreasing, then First-Fit on random orders (largest demands kept early).
    Each group is turned into a route with nearest neighbour from the depot.
    Returns routes with depots, or None if no packing within `vehicles` trucks was found.
    """
    routes = packing_insertion(demands, dist, capacity, vehicles)
    if routes is not None:
        return routes

    n = len(demands) - 1
    rng = random.Random(seed)
    order = sorted(range(1, n + 1), key=lambda c: demands[c], reverse=True)
    groups = _first_fit(order, demands, capacity, vehicles)
    for _ in range(attempts):
        if groups is not None:
            break
        # Shuffle with noise on the demand so big items still tend to come first
        noisy = sorted(range(1, n + 1), key=lambda c: demands[c] * rng.uniform(0.5, 1.5), reverse=True)
        groups = _first_fit(noisy, demands, capacity, vehicles)
    if groups is None:
        return None

    routes = []
    for group in groups:
        left = set(group)
        route = [0]
        current = 0
        while left:
            nxt = min(left, key=lambda c: dist[current][c])
            route.append(nxt)
            left.remove(nxt)
            current = nxt
        route.append(0)
        routes.append(route)
    return routes
