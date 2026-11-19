# ruff: noqa: E501  (evidence script kept as run)
"""Mining assign_buckets/tail_masks vs evaluation memberships/Slice masks on the same scores
(random, heavy ties, n from 2 to 120, buckets 2..12, tails .01/.05/.1/.5)."""

import numpy as np
import pandas as pd

from invest_evaluation.quantiles import memberships
from invest_evaluation.strategies import Slice
from invest_mining.diagnostics import assign_buckets, tail_masks

rng = np.random.default_rng(3)
bad = 0
cases = 0
for trial in range(400):
    n = int(rng.integers(2, 121))
    nb = int(rng.integers(2, 13))
    if n < nb:
        continue  # mining withholds buckets below n_buckets names (sized_dates); evaluation applies its threshold per portfolio
    s = (
        rng.integers(0, int(rng.integers(1, 40)), n).astype(float)
        if trial % 2
        else rng.normal(size=n)
    )
    names = [f"N{i}" for i in range(n)]
    wide = pd.DataFrame([s], index=[pd.Timestamp("2024-01-02")], columns=names)
    mb = assign_buckets(wide, nb, 1).iloc[0]
    dec = pd.DataFrame(
        {"decision_date": pd.Timestamp("2024-01-02"), "instrument": names, "score": s}
    )
    ev = memberships(dec, nb).set_index("instrument")
    cases += 1
    if not (mb.reindex(names).to_numpy() == ev.loc[names, "bucket"].to_numpy()).all():
        bad += 1
    for f in (0.01, 0.05, 0.1, 0.5):
        tm = tail_masks(wide, f)
        for side in ("top", "bottom"):
            em = Slice(side, f, nb).mask(ev.loc[names, "pct"], ev.loc[names, "pct_from_top"])
            if not (tm[side].iloc[0].reindex(names).to_numpy() == em.to_numpy()).all():
                bad += 1
print(
    f"cases {cases}, mismatches between mining and evaluation bucket/tail rules: {bad} (expected 0)"
)
