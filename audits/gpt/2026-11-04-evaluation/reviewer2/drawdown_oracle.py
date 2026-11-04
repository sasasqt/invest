"""Independent contract arithmetic; no repository imports or product execution.

For each historical high-water mark followed immediately by a loss, exhaustively
find its first subsequent recovery. The maximum over fully observed and elapsed
episodes is an observed lower bound if any episode remains open.
"""
from fractions import Fraction
import json


def episodes(path):
    values = [Fraction(100), *map(Fraction, path)]
    out = []
    for peak in range(len(values) - 1):
        # Repeated equal peaks restart the clock; a drawdown only starts after
        # the last high-water observation immediately before the loss.
        if values[peak] < max(values[: peak + 1]) or values[peak + 1] >= values[peak]:
            continue
        recovery = next(
            (j for j in range(peak + 1, len(values)) if values[j] >= values[peak]), None
        )
        end = len(values) - 1 if recovery is None else recovery
        trough = min(range(peak + 1, end + 1), key=values.__getitem__)
        out.append({"peak": peak, "trough": trough, "recovery": recovery,
                    "observed_duration": end - peak})
    return out


def describe(path):
    eps = episodes(path)
    return {"episodes": eps,
            "maximum_observed_duration": max((e["observed_duration"] for e in eps), default=0),
            "any_open_episode": any(e["recovery"] is None for e in eps)}


cases = {
    "closed_longest_then_short_open": ([90, 85, 90, 100, 95], 4, True),
    "open_longest": ([90, 100, 80, 85, 90], 3, True),
    "recovered_control": ([90, 85, 90, 100], 4, False),
    "equal_peaks": ([100, 100, 90, 100, 95], 2, True),
    "equal_durations": ([90, 100, 90, 95], 2, True),
    "flat_control": ([100, 100, 100], 0, False),
}
results = {}
for name, (path, maximum, open_) in cases.items():
    result = describe(path)
    assert result["maximum_observed_duration"] == maximum
    assert result["any_open_episode"] is open_
    results[name] = {"synthetic_path": path, **result}

prefix = cases["closed_longest_then_short_open"][0]
short_completion = describe([*prefix, 100])
long_completion = describe([*prefix, 95, 95, 95, 95, 100])
assert short_completion["maximum_observed_duration"] == 4
assert long_completion["maximum_observed_duration"] == 6
assert not short_completion["any_open_episode"] and not long_completion["any_open_episode"]
print(json.dumps({"scope": "trusted independent Fraction contract oracle, not product runtime",
                  "cases": results,
                  "extensions_of_identical_prefix": {"early_recovery": short_completion,
                                                      "late_recovery": long_completion},
                  "interpretation": "The prefix maximum4 is a lower bound of final maximum4 or6; the earlier maximum4 episode is recovered, while aggregate completion is uncertain.",
                  "checks": "six case expectations and two continuation controls passed"}, indent=2))
