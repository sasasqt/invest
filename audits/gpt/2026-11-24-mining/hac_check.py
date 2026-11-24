from itertools import permutations
from math import erfc, floor, sqrt
from statistics import mean


def compare(values, sessions, lags):
    mu = mean(values)
    centered = [value - mu for value in values]
    paired_sum = 0.0
    for left, x in enumerate(centered):
        for right, y in enumerate(centered):
            d = abs(sessions[left] - sessions[right])
            paired_sum += x * y * max(0, 1 - d / (lags + 1))
    se = sqrt(paired_sum) / len(values)
    t = mu / se
    return mu, se, t, erfc(t / sqrt(2)) / 2


def permutation_for(x):
    return next(
        rank
        for rank in permutations(range(1, 6))
        if abs(1 - sum((i - j) ** 2 for i, j in enumerate(rank, 1)) / 20 - x) < 1e-12
    )


n, horizon = 40, 2
L = max(horizon, floor(4 * (n / 100) ** (2 / 9)))
print("n", n, "horizon", horizon, "L", L)
for name, values in [
    ("alternating", [0.3, -0.2] * 20),
    ("clustered", [0.4] * 20 + [-0.2] * 20),
]:
    print(name, "ranks", {x: permutation_for(x) for x in sorted(set(values))})
    timings = {
        "compacted": list(range(n)),
        "contiguous+leading/trailing padding": list(range(7, 7 + n)),
        "one missing middle session": [i + (i >= 20) for i in range(n)],
        "three missing between observed": [4 * i for i in range(n)],
    }
    for kind, s in timings.items():
        print(kind, *(f"{x:.12g}" for x in compare(values, s, L)))
