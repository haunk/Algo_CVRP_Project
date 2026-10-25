"""Reading instances and solutions, and writing solutions.

Standard library only. Import as `from cvrp.io import ...` (package module,
so it does not shadow the built-in `io`).
"""


def _read_text(path):
    """Read a text file saved as UTF-8 or UTF-16.

    PowerShell's `>` writes UTF-16, so files made with `python solver.py ... > out.txt`
    on Windows start with the bytes FF FE.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def _number(token):
    """Parse a number, keeping integers as int (e.g. demands, capacity)."""
    value = float(token)
    if value.is_integer():
        return int(value)
    return value


def read_instance(path):
    """Read an instance file.

    Returns (demands, dist, capacity, vehicles).
    demands[0] is the depot. dist is a list of (n+1) lists of floats.
    Tolerates tabs, CRLF, UTF-8 or UTF-16 files, blank lines, and the Capacity/Vehicles
    lines appearing anywhere in the file.
    """
    text = _read_text(path)

    capacity = None
    vehicles = None
    rows = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        key = tokens[0].lower()
        if key.startswith("capacity") or key.startswith("vehicles"):
            # Handles "Capacity: 5", "Capacity:5" and "Capacity : 5".
            value = line.split(":", 1)[1].strip().split()[0]
            if key.startswith("capacity"):
                capacity = _number(value)
            else:
                vehicles = int(float(value))
            continue
        rows.append(tokens)

    if not rows:
        raise ValueError("instance has no data lines")
    if capacity is None:
        raise ValueError("missing 'Capacity:' line")
    if vehicles is None:
        raise ValueError("missing 'Vehicles:' line")

    demands = [_number(t) for t in rows[0]]
    size = len(demands)
    if len(rows) - 1 < size:
        raise ValueError("expected %d matrix rows, found %d" % (size, len(rows) - 1))

    dist = []
    for i in range(1, size + 1):
        dist.append([float(t) for t in rows[i]])
    return demands, dist, capacity, vehicles


def check_instance(demands, dist, capacity, vehicles):
    """Return a list of problems with the instance (empty list means OK)."""
    problems = []
    size = len(demands)
    for i in range(len(dist)):
        if len(dist[i]) != size:
            problems.append("matrix row %d has %d values, expected %d" % (i, len(dist[i]), size))
    if problems:
        return problems

    if demands[0] != 0:
        problems.append("depot demand is %s, expected 0" % demands[0])
    for i in range(size):
        if dist[i][i] != 0:
            problems.append("diagonal entry (%d,%d) is not 0" % (i, i))
        for j in range(i + 1, size):
            if abs(dist[i][j] - dist[j][i]) > 1e-9:
                problems.append("matrix not symmetric at (%d,%d)" % (i, j))
            if dist[i][j] < 0:
                problems.append("negative distance at (%d,%d)" % (i, j))
    for i in range(1, size):
        if demands[i] < 0 or demands[i] > capacity:
            problems.append("customer %d demand %s is outside [0, %s]" % (i, demands[i], capacity))
    if vehicles < 1:
        problems.append("vehicles must be at least 1")
    if sum(demands) > capacity * vehicles:
        problems.append("total demand exceeds capacity * vehicles")
    return problems


def read_solution(path):
    """Read a solution file. Returns (printed_cost, routes)."""
    lines = [line.split() for line in _read_text(path).splitlines() if line.strip()]
    if not lines:
        raise ValueError("solution file is empty")
    if len(lines[0]) != 1:
        raise ValueError("first line must contain only the total cost")
    cost = float(lines[0][0])
    routes = []
    for tokens in lines[1:]:
        routes.append([int(t) for t in tokens])
    return cost, routes


def route_cost(route, dist):
    total = 0.0
    for k in range(len(route) - 1):
        total += dist[route[k]][route[k + 1]]
    return total


def total_cost(routes, dist):
    total = 0.0
    for route in routes:
        total += route_cost(route, dist)
    return total


def format_solution(routes, dist, decimals=2):
    """Solution text: total cost on line 1, then one route per line.

    Empty routes (0 0) are skipped. The cost is recomputed here, never passed in.
    """
    kept = [r for r in routes if len(r) > 2]
    lines = ["%.*f" % (decimals, total_cost(kept, dist))]
    for route in kept:
        lines.append(" ".join(str(v) for v in route))
    return "\n".join(lines) + "\n"
