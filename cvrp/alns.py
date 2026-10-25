"""Adaptive Large Neighbourhood Search (ALNS) for CVRP.

One iteration:
  1. Destroy: remove q customers from a copy of the current solution
     (random, worst, string or route removal).
  2. Repair: insert them back (greedy insertion with blinks, or regret-2 insertion).
  3. Local search on the routes that changed.
  4. Accept the result with the simulated annealing rule. Keep the best solution seen.
  5. Every SEGMENT iterations, update the operator weights from their recent success.

Every candidate is feasible by construction: insertion respects capacity and only opens a new
route while fewer than `vehicles` routes are used. If a customer cannot be placed, the
candidate is thrown away.
"""
import math
import time

from cvrp.local_search import Solution, local_search

SEGMENT = 100              # iterations between weight updates
REACTION = 0.2             # how fast weights follow recent scores
SCORE_BEST = 33            # candidate is a new global best
SCORE_BETTER = 9           # candidate is better than the current solution
SCORE_ACCEPTED = 13        # candidate is worse but accepted (diversification)
BLINK = 0.01               # probability of skipping an insertion position (SISR "blinks")
Q_FRACTION = 0.3           # at most this share of customers is removed per iteration ...
Q_CAP = 40                 # ... and never more than this many
T_START = 1.0              # start temperature, as a multiple of the average edge length
T_END = 0.01               # end temperature, as a multiple of the average edge length


# ---------------------------------------------------------------------------
# Removal helpers
# ---------------------------------------------------------------------------

def _remove(sol, customers):
    """Take customers out of their routes. Returns the set of route indexes that changed."""
    by_route = {}
    for c in customers:
        by_route.setdefault(sol.route_of[c], set()).add(c)
    for r, gone in by_route.items():
        sol.routes[r] = [c for c in sol.routes[r] if c not in gone]
        sol.update_route(r)
    for c in customers:
        sol.route_of[c] = -1
    return set(by_route)


def random_removal(sol, q, rng, neighbors):
    n = len(sol.demands) - 1
    return rng.sample(range(1, n + 1), q)


def worst_removal(sol, q, rng, neighbors):
    """Remove customers whose detour d(p,c) + d(c,n) - d(p,n) is largest (with noise)."""
    dist = sol.dist
    scored = []
    for route in sol.routes:
        for i in range(len(route)):
            c = route[i]
            p = route[i - 1] if i > 0 else 0
            nx = route[i + 1] if i + 1 < len(route) else 0
            detour = dist[p][c] + dist[c][nx] - dist[p][nx]
            scored.append((detour * rng.uniform(0.6, 1.4), c))
    scored.sort(reverse=True)
    return [c for _, c in scored[:q]]


def string_removal(sol, q, rng, neighbors, max_string=10):
    """Remove short strings of consecutive customers from routes close to a random seed.

    Idea from SISR (Christiaens and Vanden Berghe, 2020): removing nearby strings frees space in
    several neighbouring routes at once, so the repair step can rebuild them differently.
    """
    n = len(sol.demands) - 1
    seed = rng.randint(1, n)
    removed = []
    taken = set()
    used_routes = set()
    for w in [seed] + neighbors[seed]:
        if len(removed) >= q:
            break
        r = sol.route_of[w]
        if w in taken or r in used_routes:
            continue
        used_routes.add(r)
        route = sol.routes[r]
        length = rng.randint(1, min(max_string, len(route), q - len(removed)))
        i = sol.pos[w]
        start = rng.randint(max(0, i - length + 1), min(i, len(route) - length))
        for c in route[start:start + length]:
            removed.append(c)
            taken.add(c)
    if len(removed) < q:  # seed area too small, top up with random customers
        rest = [c for c in range(1, n + 1) if c not in taken]
        removed.extend(rng.sample(rest, min(q - len(removed), len(rest))))
    return removed


def route_removal(sol, q, rng, neighbors):
    """Remove whole routes near a random seed until about q customers are out.

    Emptying routes lets the repair step merge their customers into others, which helps on
    instances with a tight vehicle limit.
    """
    n = len(sol.demands) - 1
    seed = rng.randint(1, n)
    removed = []
    seen = set()
    for w in [seed] + neighbors[seed]:
        if len(removed) >= q:
            break
        r = sol.route_of[w]
        if r in seen:
            continue
        seen.add(r)
        removed.extend(sol.routes[r])
    return removed


# ---------------------------------------------------------------------------
# Insertion helpers
# ---------------------------------------------------------------------------

def _best_insertion(sol, c, neighbors, can_open, rng, blink):
    """Cheapest feasible place for customer c.

    Checks the positions just before and after each of c's neighbours that is currently routed,
    plus a new route if `can_open` (a vehicle is free). Falls back to every position of every route.
    Returns (delta, route index or -1 for a new route, position), or None if c fits nowhere.
    """
    dist = sol.dist
    d_c = dist[c]
    dc = sol.demands[c]
    Q = sol.capacity
    routes = sol.routes
    loads = sol.loads
    route_of = sol.route_of
    pos = sol.pos

    best = None
    if can_open:
        best = (2 * d_c[0], -1, 0)

    for w in neighbors[c]:
        r = route_of[w]
        if r < 0 or loads[r] + dc > Q:
            continue
        route = routes[r]
        i = pos[w]
        prev = route[i - 1] if i > 0 else 0
        nxt = route[i + 1] if i + 1 < len(route) else 0
        d_w = dist[w]
        # before w (between prev and w)
        if not (blink and rng.random() < BLINK):
            delta = dist[prev][c] + d_c[w] - d_w[prev]
            if best is None or delta < best[0]:
                best = (delta, r, i)
        # after w (between w and nxt)
        if not (blink and rng.random() < BLINK):
            delta = d_w[c] + d_c[nxt] - d_w[nxt]
            if best is None or delta < best[0]:
                best = (delta, r, i + 1)

    if best is None:
        for r in range(len(routes)):
            if loads[r] + dc > Q or not routes[r]:
                continue
            route = routes[r]
            prev = 0
            for i in range(len(route) + 1):
                nxt = route[i] if i < len(route) else 0
                delta = dist[prev][c] + d_c[nxt] - dist[prev][nxt]
                if best is None or delta < best[0]:
                    best = (delta, r, i)
                prev = nxt
    return best


def _insert(sol, c, r, i):
    """Insert c into route r at position i (r = -1 opens a new route). Returns the route index."""
    if r == -1:
        for k in range(len(sol.routes)):
            if not sol.routes[k]:
                r = k
                break
        else:
            sol.routes.append([])
            sol.loads.append(0)
            r = len(sol.routes) - 1
        i = 0
    sol.routes[r].insert(i, c)
    sol.update_route(r)
    return r


def greedy_insertion(sol, removed, neighbors, vehicles, rng):
    """Insert customers one by one at their cheapest place, in a randomly chosen order."""
    dist = sol.dist
    demands = sol.demands
    order = rng.randrange(4)
    if order == 0:
        rng.shuffle(removed)
    elif order == 1:
        removed.sort(key=lambda c: demands[c], reverse=True)
    elif order == 2:
        removed.sort(key=lambda c: dist[0][c], reverse=True)
    else:
        removed.sort(key=lambda c: dist[0][c])
    used = sol.used_routes()
    touched = set()
    for c in removed:
        best = _best_insertion(sol, c, neighbors, used < vehicles, rng, True)
        if best is None:
            return None
        if best[1] == -1:
            used += 1
        touched.add(_insert(sol, c, best[1], best[2]))
    return touched


def regret_insertion(sol, removed, neighbors, vehicles, rng):
    """Regret-2: first insert the customer that loses most if it misses its best route.

    The two best options of each waiting customer are cached. After an insertion into route r,
    only customers that could be affected are re-evaluated: those with a neighbour in r, those
    whose cached options use r, and those relying on a new route once the fleet is full.
    """
    pending = list(removed)
    rng.shuffle(pending)
    used = sol.used_routes()
    options = {}
    for c in pending:
        options[c] = _two_best_routes(sol, c, neighbors, used < vehicles)
    touched = set()
    while pending:
        pick = None
        pick_score = None
        for c in pending:
            first, second = options[c]
            if first is None:
                return None
            # A customer with only one option gets top priority
            regret = (second[0] - first[0]) if second is not None else float("inf")
            if pick is None or regret > pick_score:
                pick, pick_score = c, regret
        place = options[pick][0]
        pending.remove(pick)
        if place[1] == -1:
            used += 1
        r = _insert(sol, pick, place[1], place[2])
        touched.add(r)

        fleet_full = used >= vehicles
        route_of = sol.route_of
        for c in pending:
            first, second = options[c]
            stale = (first[1] == r or (second is not None and second[1] == r)
                     or (fleet_full and (first[1] == -1 or (second is not None and second[1] == -1))))
            if not stale:
                for w in neighbors[c]:
                    if route_of[w] == r:
                        stale = True
                        break
            if stale:
                options[c] = _two_best_routes(sol, c, neighbors, not fleet_full)
    return touched


def _two_best_routes(sol, c, neighbors, can_open):
    """Best insertion of c in each candidate route. Returns the best and second best (different routes)."""
    dist = sol.dist
    d_c = dist[c]
    dc = sol.demands[c]
    Q = sol.capacity
    routes = sol.routes
    loads = sol.loads
    route_of = sol.route_of
    pos = sol.pos

    per_route = {}
    if can_open:
        per_route[-1] = (2 * d_c[0], -1, 0)
    for w in neighbors[c]:
        r = route_of[w]
        if r < 0 or loads[r] + dc > Q:
            continue
        route = routes[r]
        i = pos[w]
        prev = route[i - 1] if i > 0 else 0
        nxt = route[i + 1] if i + 1 < len(route) else 0
        d_w = dist[w]
        for delta, p in ((dist[prev][c] + d_c[w] - d_w[prev], i), (d_w[c] + d_c[nxt] - d_w[nxt], i + 1)):
            old = per_route.get(r)
            if old is None or delta < old[0]:
                per_route[r] = (delta, r, p)

    if not per_route:
        best = _best_insertion(sol, c, neighbors, can_open, None, False)
        return best, None
    ranked = sorted(per_route.values())
    return ranked[0], (ranked[1] if len(ranked) > 1 else None)


DESTROY = [random_removal, worst_removal, string_removal, route_removal]
REPAIR = [greedy_insertion, regret_insertion]


def _roulette(weights, rng):
    total = sum(weights)
    pick = rng.random() * total
    for k in range(len(weights)):
        pick -= weights[k]
        if pick <= 0:
            return k
    return len(weights) - 1


def alns(start, neighbors, vehicles, deadline, rng, log=None):
    """Run ALNS from the Solution `start` until `deadline` (a time.perf_counter() value).

    Returns (best Solution, number of iterations). `start` must be feasible.
    """
    n = len(start.demands) - 1
    current = start.copy()
    current_cost = current.cost()
    best = current.copy()
    best_cost = current_cost
    if n < 2:
        return best, 0

    # Removal size: between q_min and q_max customers
    q_max = min(n - 1, max(10, min(Q_CAP, int(Q_FRACTION * n))))
    q_min = min(q_max, 5)

    # Temperature relative to the average edge length, cooled geometrically over the time budget
    avg_edge = max(current_cost / (n + current.used_routes()), 1e-9)  # guard against all-zero distances
    t_start = T_START * avg_edge
    t_end = T_END * avg_edge
    begin = time.perf_counter()
    budget = max(deadline - begin, 1e-6)

    d_weights = [1.0] * len(DESTROY)
    r_weights = [1.0] * len(REPAIR)
    d_scores = [0.0] * len(DESTROY)
    r_scores = [0.0] * len(REPAIR)
    d_uses = [0] * len(DESTROY)
    r_uses = [0] * len(REPAIR)

    iteration = 0
    while True:
        now = time.perf_counter()
        if now >= deadline:
            break
        iteration += 1
        frac = (now - begin) / budget
        temperature = t_start * (t_end / t_start) ** frac

        di = _roulette(d_weights, rng)
        ri = _roulette(r_weights, rng)
        d_uses[di] += 1
        r_uses[ri] += 1

        cand = current.copy()
        q = rng.randint(q_min, q_max)
        removed = DESTROY[di](cand, q, rng, neighbors)
        touched = _remove(cand, removed)
        inserted = REPAIR[ri](cand, removed, neighbors, vehicles, rng)
        if inserted is None:
            continue  # a customer could not be placed, drop this candidate
        touched |= inserted
        start_customers = [c for r in touched for c in cand.routes[r]]
        local_search(cand, neighbors, deadline, start_customers)
        cand_cost = cand.cost()

        # Simulated annealing acceptance: always take better, sometimes take worse
        score = 0
        if cand_cost < current_cost - 1e-9:
            score = SCORE_BETTER
            accept = True
        else:
            accept = rng.random() < math.exp(-(cand_cost - current_cost) / temperature)
            if accept:
                score = SCORE_ACCEPTED
        if accept:
            current, current_cost = cand, cand_cost
            if cand_cost < best_cost - 1e-9:
                best, best_cost = cand.copy(), cand_cost
                score = SCORE_BEST
                if log:
                    log("  it %d  t=%.1fs  best=%.2f  (%s + %s)" % (
                        iteration, now - begin, best_cost, DESTROY[di].__name__, REPAIR[ri].__name__))
        d_scores[di] += score
        r_scores[ri] += score

        if iteration % SEGMENT == 0:
            for k in range(len(DESTROY)):
                if d_uses[k]:
                    d_weights[k] = (1 - REACTION) * d_weights[k] + REACTION * d_scores[k] / d_uses[k]
                d_weights[k] = max(d_weights[k], 0.1)
            for k in range(len(REPAIR)):
                if r_uses[k]:
                    r_weights[k] = (1 - REACTION) * r_weights[k] + REACTION * r_scores[k] / r_uses[k]
                r_weights[k] = max(r_weights[k], 0.1)
            d_scores = [0.0] * len(DESTROY)
            r_scores = [0.0] * len(REPAIR)
            d_uses = [0] * len(DESTROY)
            r_uses = [0] * len(REPAIR)

    best.remove_empty_routes()
    return best, iteration
