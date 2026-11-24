from itertools import permutations
from math import erfc, floor, sqrt
from statistics import NormalDist, mean


def rank_ic(factor_ranks, outcome_ranks):
    return 1 - sum((f - y) ** 2 for f, y in zip(factor_ranks, outcome_ranks)) / 20


def ascending_ranks(values):
    ordered = sorted(values)
    if len(set(values)) != len(values):
        raise ValueError("test helper accepts either distinct ranks or a fully constant row")
    return [ordered.index(value) + 1 for value in values]


def hac_at_sessions(observed, sessions, bandwidth):
    mu = mean(observed)
    centered = [value - mu for value in observed]
    paired_sum = sum(
        x * y * max(0, 1 - abs(a - b) / (bandwidth + 1))
        for a, x in zip(sessions, centered)
        for b, y in zip(sessions, centered)
    )
    se = sqrt(paired_sum) / len(observed)
    t = mu / se
    return mu, se, t, 1 - NormalDist().cdf(t), erfc(t / sqrt(2)) / 2


count, horizon = 60, 1
label_ranks = (1, 2, 3, 4, 5)
attainable = {
    target: next(p for p in permutations(label_ranks) if abs(rank_ic(p, label_ranks) - target) < 1e-12)
    for target in (0.6, -0.4)
}
bandwidth = max(horizon, floor(4 * (count / 100) ** (2 / 9)))
print("attainable", attainable, "L", bandwidth)
for spacing in (1, 4):
    last_decision = spacing * (count - 1)
    opens = [[100 * (1 + rank * 0.001) ** t for rank in label_ranks] for t in range(last_decision + 3)]
    favorable = (0.6, -0.4)
    observed = []
    actual_indices = []
    for t in range(last_decision + 1):
        q, r = divmod(t, spacing)
        # Scale-free fixed factor intraday_return, constant exactly on intervening sessions.
        ranks = attainable[favorable[q % 2]] if r == 0 else (0, 0, 0, 0, 0)
        close = [open_ * (1 + rank * 0.001) for open_, rank in zip(opens[t], ranks)]
        scores = [c / o - 1 for c, o in zip(close, opens[t])]
        labels = [exit_ / entry - 1 for entry, exit_ in zip(opens[t + 1], opens[t + 2])]
        if len(set(scores)) > 1:
            observed.append(rank_ic(ascending_ranks(scores), ascending_ranks(labels)))
            actual_indices.append(t)
    assert len(observed) == count and last_decision + 1 >= count
    print("spacing", spacing, "label dates", last_decision + 1, "valid ICs", len(observed))
    print("compacted", hac_at_sessions(observed, list(range(count)), bandwidth))
    print("session-clock", hac_at_sessions(observed, actual_indices, bandwidth))
