"""Solution representation and granular local search.

Inside the search a route is a list of customers WITHOUT the depot, for example [3, 1, 7].
The depot is added back only when the solution is printed (see Solution.to_routes).

Local search idea (granular neighbourhood): for every customer u and each of its k nearest
customers v, try a few moves that bring u next to v. Every move is checked with delta
evaluation (only the changed edges), so one check costs a handful of lookups.

Moves tried for a pair (u, v), where x = next(u), pu = prev(u), y = next(v), pv = prev(v):
  1. relocate u after v           5. 2-opt inside one route (creates edge u-v)
  2. relocate u before v          6. 2-opt* : u v joined, rest reversed (creates edge u-v)
  3. Or-opt: move (u, x) after v  7. 2-opt* : tail swap so that v follows u
  4. swap u and v
"""
import time

EPS = 1e-9


class Solution:
    """Routes plus index arrays that make every move O(1) to evaluate.

    routes[r]   list of customers in route r (may be empty)
    route_of[c] route index of customer c
    pos[c]      position of c inside its route
    cum[c]      load of its route from the start up to and including c
    prev[c]     customer before c in its route (0 = depot)
    next[c]     customer after c in its route (0 = depot)
    loads[r]    total demand of route r
    """

    def __init__(self, routes, demands, dist, capacity):
        self.demands = demands
        self.dist = dist
        self.capacity = capacity
        n = len(demands) - 1
        self.route_of = [-1] * (n + 1)
        self.pos = [0] * (n + 1)
        self.cum = [0] * (n + 1)
        self.prev = [0] * (n + 1)
        self.next = [0] * (n + 1)
        self.routes = [list(r) for r in routes]
        self.loads = [0] * len(self.routes)
        for r in range(len(self.routes)):
            self.update_route(r)

    @classmethod
    def from_depot_routes(cls, routes, demands, dist, capacity):
        """Build from routes in printed form ([0, 1, 2, 0])."""
        return cls([r[1:-1] for r in routes if len(r) > 2], demands, dist, capacity)

    def copy(self):
        new = Solution.__new__(Solution)
        new.demands = self.demands
        new.dist = self.dist
        new.capacity = self.capacity
        new.routes = [r[:] for r in self.routes]
        new.route_of = self.route_of[:]
        new.pos = self.pos[:]
        new.cum = self.cum[:]
        new.prev = self.prev[:]
        new.next = self.next[:]
        new.loads = self.loads[:]
        return new

    def update_route(self, r):
        """Recompute the indexes of route r after it changed."""
        route = self.routes[r]
        demands = self.demands
        route_of = self.route_of
        pos = self.pos
        cum = self.cum
        prev = self.prev
        nxt = self.next
        load = 0
        last = 0
        for i in range(len(route)):
            c = route[i]
            load += demands[c]
            route_of[c] = r
            pos[c] = i
            cum[c] = load
            prev[c] = last
            nxt[last] = c
            last = c
        nxt[last] = 0
        nxt[0] = 0  # the depot entry is scratch space, never read
        self.loads[r] = load

    def route_cost(self, r):
        route = self.routes[r]
        if not route:
            return 0.0
        dist = self.dist
        total = dist[0][route[0]] + dist[route[-1]][0]
        for i in range(len(route) - 1):
            total += dist[route[i]][route[i + 1]]
        return total

    def cost(self):
        return sum(self.route_cost(r) for r in range(len(self.routes)))

    def used_routes(self):
        return sum(1 for r in self.routes if r)

    def remove_empty_routes(self):
        self.routes = [r for r in self.routes if r]
        self.loads = [0] * len(self.routes)
        for r in range(len(self.routes)):
            self.update_route(r)

    def to_routes(self):
        """Routes in printed form, empty routes skipped."""
        return [[0] + r + [0] for r in self.routes if r]


def local_search(sol, neighbors, deadline, start_customers=None, rng=None):
    """Improve `sol` in place until no move helps or the deadline passes.

    neighbors[u]      closest customers of u (granular neighbourhood)
    start_customers   customers to examine first (default: all). Customers in routes changed
                      by an applied move are examined again, so the search ends at a local
                      optimum for the examined part of the solution.
    Returns the total improvement (a negative number or 0).
    """
    dist = sol.dist
    demands = sol.demands
    Q = sol.capacity
    routes = sol.routes
    route_of = sol.route_of
    pos = sol.pos
    cum = sol.cum
    prv = sol.prev
    nxt = sol.next
    loads = sol.loads

    n = len(demands) - 1
    if start_customers is None:
        queue = list(range(1, n + 1))
        if rng is not None:
            rng.shuffle(queue)
    else:
        queue = list(start_customers)
    in_queue = [False] * (n + 1)
    for c in queue:
        in_queue[c] = True

    total_gain = 0.0
    checks = 0
    head = 0
    while head < len(queue):
        checks += 1
        if checks & 127 == 0 and time.perf_counter() > deadline:
            break
        u = queue[head]
        head += 1
        in_queue[u] = False

        changed = _improve_customer(u, neighbors[u], dist, demands, Q, routes, route_of, pos, cum, prv, nxt, loads)
        if changed is None:
            continue
        gain, touched = changed
        total_gain += gain
        for r in touched:
            sol.update_route(r)
        for r in touched:
            for c in routes[r]:
                if not in_queue[c]:
                    in_queue[c] = True
                    queue.append(c)
        if head > 100000:
            # Drop the processed part of the queue so it does not grow forever
            queue = queue[head:]
            head = 0
    return total_gain


def _improve_customer(u, neigh_u, dist, demands, Q, routes, route_of, pos, cum, prv, nxt, loads):
    """Try all moves between u and its neighbours. Apply the first improving one.

    Returns (delta, touched route indexes) or None if no improving move was found.
    """
    ru = route_of[u]
    route_u = routes[ru]
    iu = pos[u]
    pu = prv[u]
    x = nxt[u]
    du = demands[u]
    d_u = dist[u]
    d_pu = dist[pu]
    remove_u = d_pu[x] - d_pu[u] - d_u[x]     # change in cost from taking u out of its route
    load_ru = loads[ru]
    cum_u = cum[u]

    # Values for the Or-opt move of the pair (u, x)
    if x != 0:
        xx = nxt[x]
        dux = du + demands[x]
        remove_ux = d_pu[xx] - d_pu[u] - dist[x][xx]
    else:
        xx = -1

    for v in neigh_u:
        rv = route_of[v]
        route_v = routes[rv]
        iv = pos[v]
        pv = prv[v]
        y = nxt[v]
        d_v = dist[v]
        same = ru == rv
        dv = demands[v]

        # 1. Relocate u after v (between v and y)
        if v != pu and (same or loads[rv] + du <= Q):
            delta = remove_u + d_v[u] + d_u[y] - d_v[y]
            if delta < -EPS:
                route_u.pop(iu)
                if same:
                    route_u.insert(route_u.index(v) + 1, u)
                    return delta, (ru,)
                route_v.insert(iv + 1, u)
                return delta, (ru, rv)

        # 2. Relocate u before v (between pv and v)
        if v != x and (same or loads[rv] + du <= Q):
            delta = remove_u + dist[pv][u] + d_u[v] - dist[pv][v]
            if delta < -EPS:
                route_u.pop(iu)
                if same:
                    route_u.insert(route_u.index(v), u)
                    return delta, (ru,)
                route_v.insert(iv, u)
                return delta, (ru, rv)

        # 3. Or-opt: move the pair (u, x) after v, in either orientation
        if xx != -1 and v != x and v != pu and (same or loads[rv] + dux <= Q):
            d_x = dist[x]
            forward = d_v[u] + d_x[y] - d_v[y]       # v u x y
            backward = d_v[x] + d_u[y] - d_v[y]      # v x u y
            ins = forward if forward <= backward else backward
            delta = remove_ux + ins
            if delta < -EPS:
                pair = [u, x] if forward <= backward else [x, u]
                del route_u[iu:iu + 2]
                if same:
                    k = route_u.index(v) + 1
                    route_u[k:k] = pair
                    return delta, (ru,)
                route_v[iv + 1:iv + 1] = pair
                return delta, (ru, rv)

        # 4. Swap u and v (skip neighbours in the same route, the formula needs distinct edges)
        if not (same and (v == x or v == pu)):
            if same or (load_ru - du + dv <= Q and loads[rv] - dv + du <= Q):
                delta = (d_pu[v] + d_v[x] - d_pu[u] - d_u[x]
                         + dist[pv][u] + d_u[y] - dist[pv][v] - d_v[y])
                if delta < -EPS:
                    route_u[iu] = v
                    route_v[iv] = u
                    return delta, ((ru,) if same else (ru, rv))

        if same:
            # 5. 2-opt: reverse the part between u and v so that u and v become neighbours
            if iu < iv and v != x:
                delta = d_u[v] + dist[x][y] - d_u[x] - d_v[y]
                if delta < -EPS:
                    route_u[iu + 1:iv + 1] = route_u[iu + 1:iv + 1][::-1]
                    return delta, (ru,)
            elif iu > iv and pu != v:
                delta = dist[pv][pu] + d_v[u] - dist[pv][v] - d_pu[u]
                if delta < -EPS:
                    route_u[iv:iu] = route_u[iv:iu][::-1]
                    return delta, (ru,)
        else:
            # 6. 2-opt*: [.. u] + [v ..]^reversed and [.. x]^reversed... Concretely
            #    route u: A u x B, route v: C v y D  ->  A u v C^r  and  B^r x y D
            load1 = cum_u + cum[v]
            load2 = (load_ru - cum_u) + (loads[rv] - cum[v])
            if load1 <= Q and load2 <= Q:
                delta = d_u[v] + dist[x][y] - d_u[x] - d_v[y]
                if delta < -EPS:
                    new_u = route_u[:iu + 1] + route_v[:iv + 1][::-1]
                    new_v = route_u[iu + 1:][::-1] + route_v[iv + 1:]
                    routes[ru] = new_u
                    routes[rv] = new_v
                    return delta, (ru, rv)

            # 7. 2-opt* tail swap so that v follows u:
            #    route u: A u x B, route v: C pv v D  ->  A u v D  and  C pv x B
            cum_pv = cum[pv] if pv != 0 else 0
            load1 = cum_u + (loads[rv] - cum_pv)
            load2 = cum_pv + (load_ru - cum_u)
            if load1 <= Q and load2 <= Q:
                delta = d_u[v] + dist[pv][x] - d_u[x] - dist[pv][v]
                if delta < -EPS:
                    new_u = route_u[:iu + 1] + route_v[iv:]
                    new_v = route_v[:iv] + route_u[iu + 1:]
                    routes[ru] = new_u
                    routes[rv] = new_v
                    return delta, (ru, rv)
    return None
