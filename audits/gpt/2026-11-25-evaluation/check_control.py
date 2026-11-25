"""Independently authored arithmetic for a 2024 toy benchmark; no product imports."""
from fractions import Fraction
from math import prod, sqrt
from statistics import mean, stdev

N = 23
ANNUALIZATION = 252
EVENT = 2  # With first evaluation at market index 2, market index 4 is row 2.
THIRD = Fraction(1, 3)
SETTLED_EVENT = mean([Fraction(0, 10) - 1, Fraction(0), Fraction(0)])

def event_series(event_return):
    return [Fraction(0)] * EVENT + [event_return] + [Fraction(0)] * (N - EVENT - 1)

def run(name, strategy, benchmark):
    active = [r - b for r, b in zip(strategy, benchmark, strict=True)]
    tracking_error = stdev(active)
    ir = float(mean(active)) / tracking_error * sqrt(ANNUALIZATION) if tracking_error else None
    check = "undefined" if ir is None else "pass" if ir > 0 else "fail"
    print(
        name, "event return:", str(benchmark[EVENT]),
        "aligned returns:", N, "total:", str(prod(1 + b for b in benchmark) - 1),
        "annualized tracking error:", tracking_error * sqrt(ANNUALIZATION),
        "annualized IR:", ir, "optional IR check:", check,
    )

assert SETTLED_EVENT == -THIRD
strategy = event_series(-THIRD)  # Strategy cash settlement and weights held fixed.
run("settled", strategy, event_series(SETTLED_EVENT))
run("settlement omitted", strategy, event_series(Fraction(0)))
