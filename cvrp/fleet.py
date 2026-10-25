"""Route elimination: bring the number of routes down to the vehicle limit.

Used when construction gives more routes than vehicles and the simple repair fails, which
happens when trucks must be almost full (tight fleet instances).

Idea (an ejection pool):
  1. Empty the route with the smallest load. Its customers go into a pool.
  2. Repeat until the pool is empty:
     a. Consolidate: move or swap customers between nearby routes whenever this makes full
        routes fuller (it increases the sum of squared route loads). Free capacity then
        gathers in a few routes instead of being spread thinly over all of them.
     b. Fill: insert pool customers, largest demand first, wherever they fit (no new routes).
     c. Eject: push the biggest pool customer into a route, ejecting 1 or 2 customers with
        smaller total demand. The pool trades big customers for small ones.
     d. If no ejection is possible: remove a few customers near a pool customer and insert
        everything again, keeping the change if the pool demand did not grow.
  3. Repeat until the route count is within the limit or time runs out.

Distance is mostly ignored here. ALNS fixes the cost afterwards.
"""
import time

from cvrp.alns import _best_insertion, _insert, _remove

EPS = 1e-9


def _cheapest_position(sol, c, r):
    """Position in route r where inserting c adds the least distance."""
    dist = sol.dist
    route = sol.routes[r]
    best_pos, best_delta = 0, None
    prev = 0
    for i in range(len(route) + 1):
        nxt = route[i] if i < len(route) else 0
        delta = dist[prev][c] + dist[c][nxt] - dist[prev][nxt]
        if best_delta is None or delta < best_delta:
            best_pos, best_delta = i, delta
        prev = nxt
    return best_pos


def _fill(sol, pool, neighbors, rng):
    """Insert pool customers (largest demand first) without opening routes. Returns the leftovers."""
    demands = sol.demands
    rng.shuffle(pool)  # random order among equal demands
    pool.sort(key=lambda c: demands[c], reverse=True)
    left = []
    for c in pool:
        best = _best_insertion(sol, c, neighbors, False, None, False)
        if best is None:
            left.append(c)
        else:
            _insert(sol, c, best[1], best[2])
    return left


def _consolidate(sol, neighbors, rng, deadline, everywhere=False):
    """Move/swap customers towards fuller routes until the sum of squared loads stops growing.

    Moving demand d from a route with load L1 to one with load L2 increases L1^2 + L2^2
    exactly when L2 > L1 - d. A swap that moves net demand d works the same way.
    Target routes are those of the customer's neighbours, or all routes if `everywhere`.
    """
    demands = sol.demands
    Q = sol.capacity
    loads = sol.loads
    route_of = sol.route_of
    routes = sol.routes
    customers = [c for c in range(1, len(demands)) if route_of[c] >= 0]
    improved = True
    while improved and time.perf_counter() < deadline:
        improved = False
        rng.shuffle(customers)
        for a in customers:
            r1 = route_of[a]
            da = demands[a]
            if everywhere:
                targets = {r for r in range(len(routes)) if routes[r]}
            else:
                targets = {route_of[w] for w in neighbors[a]}
            targets.discard(r1)
            targets.discard(-1)
            for r2 in sorted(targets, key=lambda r: loads[r], reverse=True):
                L1 = loads[r1]
                L2 = loads[r2]
                if L2 + da <= Q and L2 > L1 - da + EPS:
                    # relocate a into r2
                    routes[r1].remove(a)
                    sol.update_route(r1)
                    _insert(sol, a, r2, _cheapest_position(sol, a, r2))
                    improved = True
                    break
                swapped = False
                for b in routes[r2]:
                    d = da - demands[b]
                    if d > EPS and L2 + d <= Q and L2 > L1 - d + EPS:
                        # swap a and b in place
                        i, j = sol.pos[a], sol.pos[b]
                        routes[r1][i] = b
                        routes[r2][j] = a
                        sol.update_route(r1)
                        sol.update_route(r2)
                        swapped = True
                        break
                if swapped:
                    improved = True
                    break


def _eject_insert(sol, c, rng):
    """Force pool customer c into a route, pushing out 1 or 2 customers to make room.

    Only moves where the ejected demand is strictly smaller than demand[c] are made, so the
    pool shrinks in demand each time. Picks the smallest ejected demand (ties broken at random).
    Returns the ejected customers, or None if no such move exists.
    """
    demands = sol.demands
    Q = sol.capacity
    dc = demands[c]
    best = None
    best_key = None
    for r in range(len(sol.routes)):
        route = sol.routes[r]
        if not route:
            continue
        need = sol.loads[r] + dc - Q
        if need <= 0:
            options = [[]]
        else:
            options = [[a] for a in route if need <= demands[a] < dc]
            for i in range(len(route)):
                da = demands[route[i]]
                if da >= need:
                    continue  # a single customer already covers it
                for j in range(i + 1, len(route)):
                    s = da + demands[route[j]]
                    if need <= s < dc:
                        options.append([route[i], route[j]])
        for ejected in options:
            key = (sum(demands[a] for a in ejected), rng.random())
            if best_key is None or key < best_key:
                best, best_key = (r, ejected), key
    if best is None:
        return None

    r, ejected = best
    if ejected:
        _remove(sol, ejected)
    _insert(sol, c, r, _cheapest_position(sol, c, r))
    return ejected


def reduce_routes(sol, neighbors, vehicles, deadline, rng, log=None):
    """Try to make `sol` use at most `vehicles` routes. Changes sol in place.

    Returns True on success. On failure sol holds the last complete solution (every customer
    routed, capacity respected) but may still use too many routes.
    """
    demands = sol.demands
    n = len(demands) - 1
    q_max = max(2, min(15, n // 10))
    while sol.used_routes() > vehicles:
        if time.perf_counter() > deadline:
            return False
        before = sol.copy()

        # 1. Empty the lightest route
        r = min((k for k in range(len(sol.routes)) if sol.routes[k]), key=lambda k: sol.loads[k])
        pool = list(sol.routes[r])
        _remove(sol, pool)

        # 2. Consolidate, fill, eject or perturb until the pool is empty
        rounds = 0
        while time.perf_counter() < deadline:
            rounds += 1
            # Nearby moves keep routes compact. Every 5th round allow moves to any route.
            _consolidate(sol, neighbors, rng, deadline, everywhere=(rounds % 5 == 0))
            pool = _fill(sol, pool, neighbors, rng)
            if not pool:
                break
            pool.sort(key=lambda c: demands[c], reverse=True)
            k = 0 if rng.random() < 0.7 else rng.randrange(len(pool))
            ejected = _eject_insert(sol, pool[k], rng)
            if ejected is not None:
                pool.pop(k)
                pool.extend(ejected)
                continue

            backup = sol.copy()
            old_pool = pool[:]
            old_demand = sum(demands[c] for c in pool)
            seed = rng.choice(pool)
            q = rng.randint(1, q_max)
            removed = [w for w in neighbors[seed] if sol.route_of[w] >= 0][:q]
            _remove(sol, removed)
            pool = _fill(sol, pool + removed, neighbors, rng)
            if sum(demands[c] for c in pool) > old_demand:
                sol.__dict__.update(backup.__dict__)  # undo
                pool = old_pool

        if pool:
            sol.__dict__.update(before.__dict__)  # out of time: keep the last complete solution
            return False
        if log:
            log("route elimination: %d routes (%d rounds)" % (sol.used_routes(), rounds))
    sol.remove_empty_routes()
    return True
