import json
import os

from invest_data.bundle import read_bundle
from invest_data.schemas import publish_signals

m, bars = read_bundle("out/market")
close = bars.pivot(index="date", columns="instrument", values="close")
score = -(close / close.shift(1) - 1)
s = score.stack().rename("score").reset_index()
s.columns = ["decision_date", "instrument", "score"]
publish_signals(
    s.dropna(),
    "out/signals",
    dataset_id="wk-signals",
    metadata={"factor_id": "rev1w", "horizon_days": 1},
)
cfg = json.load(
    open(os.environ["INVEST"] + "/strategy-evaluation/examples/quantile_long_short.json")
)
cfg["execution"]["min_price"] = 0.0
cfg["costs"].update({"adv_window": 4, "vol_window": 4})
json.dump(cfg, open("out/config.json", "w"))
