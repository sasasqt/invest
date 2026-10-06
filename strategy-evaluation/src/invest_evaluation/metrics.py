"""Strategy metrics following strategy-evaluation/METRICS.md.

Every metric is a :class:`Metric` with a value *and* a status, so undefined results
(zero dispersion, no losses, insolvency, too few observations) are explicit instead of
silently becoming 0, infinity or a misleading number. Conventions:

* simple periodic returns from a unit wealth index that starts at ``V0`` (initial capital);
* sample statistics use ``ddof=1``; annualisation by ``A`` periods per year;
* CAGR uses elapsed years ``N / A`` (the trading-period convention);
* annual risk-free / MAR rates convert to per-period rates as ``(1 + r)^(1/A) - 1``;
* drawdowns include ``V0`` in the running peak and are reported as positive magnitudes.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from invest_evaluation.engine import COST_KINDS, BacktestResult


@dataclass(frozen=True)
class Metric:
    value: float | int | str | None
    unit: str
    status: str = "ok"
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        v = out["value"]
        if isinstance(v, float) and not math.isfinite(v):
            out["value"], out["status"] = None, "undefined"
            out["reason"] = out["reason"] or "non_finite"
        if not out["extra"]:
            del out["extra"]
        return out


def _ok(value: float | int | str | None, unit: str, **extra: Any) -> Metric:
    return Metric(value, unit, extra=extra)


def _undef(unit: str, reason: str, status: str = "undefined") -> Metric:
    return Metric(None, unit, status=status, reason=reason)


def period_rate(annual: float, periods: int) -> float:
    return float((1.0 + annual) ** (1.0 / periods) - 1.0)


# ---------------------------------------------------------------------------
# Return-series metrics


def drawdown_series(wealth: pd.Series, v0: float) -> pd.Series:
    """Signed drawdown D_t = V_t / max(V_0..V_t) - 1."""
    peak = np.maximum.accumulate(np.concatenate([[v0], wealth.to_numpy()]))[1:]
    return pd.Series(wealth.to_numpy() / peak - 1.0, index=wealth.index, name="drawdown")


def drawdown_metrics(wealth: pd.Series, v0: float) -> dict[str, Metric]:
    dd = drawdown_series(wealth, v0)
    values = np.concatenate([[v0], wealth.to_numpy()])
    dates = [None, *wealth.index]
    peak_i = 0
    worst = (0.0, 0, 0)  # (drawdown, peak index, trough index)
    episodes: list[tuple[int, int, int | None]] = []  # (peak, trough, recovery or None)
    start: int | None = None
    trough = 0
    for k in range(1, len(values)):
        if values[k] >= values[peak_i]:
            if start is not None:
                episodes.append((start, trough, k))
                start = None
            peak_i = k
            continue
        d = values[k] / values[peak_i] - 1.0
        if start is None:
            start, trough = peak_i, k
        if values[k] < values[trough]:
            trough = k
        if d < worst[0]:
            worst = (d, peak_i, k)
    if start is not None:
        episodes.append((start, trough, None))

    max_dd = -worst[0]
    durations = [(r if r is not None else len(values) - 1) - p for p, _, r in episodes]
    recovered = [r - t for _, t, r in episodes if r is not None]
    recovery_of_worst = next((r for p, t, r in episodes if p == worst[1] and t == worst[2]), None)
    out = {
        "max_drawdown": _ok(
            float(max_dd),
            "fraction",
            peak_date=str(dates[worst[1]].date()) if worst[1] else "start",
            trough_date=str(dates[worst[2]].date()) if worst[2] else None,
            recovery_date=(
                str(dates[recovery_of_worst].date()) if recovery_of_worst is not None else None
            ),
        ),
        "current_drawdown": _ok(float(-dd.iloc[-1]), "fraction"),
        "max_drawdown_duration": _ok(
            max(durations, default=0),
            "sessions",
            censored=bool(episodes and episodes[-1][2] is None),
        ),
        "max_recovery_duration": (
            _ok(max(recovered), "sessions")
            if recovered
            else _undef("sessions", "no_recovered_drawdown", "not_applicable")
        ),
        "time_under_water": _ok(float((dd < 0).mean()), "fraction"),
        "average_drawdown": _ok(float(-dd.mean()), "fraction"),
        "drawdown_episodes": _ok(len(episodes), "count"),
        "ulcer_index": _ok(float(np.sqrt(np.mean(dd.to_numpy() ** 2))), "fraction"),
    }
    return out


def return_metrics(
    returns: pd.Series,
    *,
    v0: float,
    annualization: int,
    risk_free_annual: float = 0.0,
    mar_annual: float = 0.0,
) -> dict[str, Metric]:
    r = returns.to_numpy(dtype=float)
    n = len(r)
    a = annualization
    out: dict[str, Metric] = {"periods": _ok(n, "count")}
    if n < 2:
        out["status"] = _undef("", "fewer_than_two_returns", "insufficient_data")
        return out
    wealth = pd.Series(v0 * np.cumprod(1 + r), index=returns.index)
    if (wealth <= 0).any():
        first = wealth.index[int(np.argmax(wealth.to_numpy() <= 0))]
        out["insolvency"] = _ok(str(first.date()), "date")
        out["total_return"] = _ok(float(wealth.iloc[-1] / v0 - 1), "fraction")
        out.update(drawdown_metrics(wealth, v0))
        for key in ("cagr", "sharpe", "sortino", "calmar"):
            unit = "fraction/year" if key == "cagr" else "ratio"
            out[key] = _undef(unit, "insolvent_wealth_path", "invalid_input")
        return out

    rf = period_rate(risk_free_annual, a)
    mar = period_rate(mar_annual, a)
    excess = r - rf
    mean, std = float(r.mean()), float(r.std(ddof=1))
    years = n / a
    total = float(wealth.iloc[-1] / v0 - 1)
    cagr = float((wealth.iloc[-1] / v0) ** (1 / years) - 1)
    downside = float(np.sqrt(np.mean(np.minimum(r - mar, 0.0) ** 2)))
    dd = drawdown_metrics(wealth, v0)
    max_dd = float(dd["max_drawdown"].value or 0.0)
    ulcer = float(dd["ulcer_index"].value or 0.0)
    gains = float(np.sum(np.maximum(r - mar, 0)))
    losses = float(np.sum(np.maximum(mar - r, 0)))
    neg_sum = float(-r[r < 0].sum())
    ex_std = float(excess.std(ddof=1))

    out.update(
        {
            "total_return": _ok(total, "fraction"),
            "cagr": _ok(cagr, "fraction/year", day_count="periods/annualization"),
            "mean_return": _ok(mean, "fraction/period"),
            "median_return": _ok(float(np.median(r)), "fraction/period"),
            "geometric_mean_return": _ok(
                float((wealth.iloc[-1] / v0) ** (1 / n) - 1), "fraction/period"
            ),
            "annual_arithmetic_mean": _ok(mean * a, "fraction/year"),
            "variance_return": _ok(float(r.var(ddof=1)), "fraction^2"),
            "annual_volatility": _ok(std * math.sqrt(a), "fraction/year^0.5"),
            "downside_deviation": _ok(downside, "fraction/period", mar_period=mar),
            "annual_downside_volatility": _ok(downside * math.sqrt(a), "fraction/year^0.5"),
            "sharpe": (
                _ok(float(excess.mean() / ex_std * math.sqrt(a)), "ratio")
                if ex_std > 1e-15
                else _undef("ratio", "zero_excess_return_dispersion")
            ),
            "sortino": (
                _ok(float((r - mar).mean() * a / (downside * math.sqrt(a))), "ratio")
                if downside > 1e-15
                else _undef("ratio", "no_returns_below_mar")
            ),
            "calmar": (
                _ok(cagr / max_dd, "ratio")
                if max_dd > 1e-15
                else _undef("ratio", "zero_max_drawdown")
            ),
            "martin": (
                _ok(float((r - mar).mean() * a / ulcer), "ratio")
                if ulcer > 1e-15
                else _undef("ratio", "zero_ulcer_index")
            ),
            "omega": (
                _ok(gains / losses, "ratio")
                if losses > 1e-15
                else _undef("ratio", "no_returns_below_mar")
            ),
            "gain_to_pain": (
                _ok(float(r.sum()) / neg_sum, "ratio")
                if neg_sum > 1e-15
                else _undef("ratio", "no_negative_returns")
            ),
            "hit_rate": _ok(float((r > 0).mean()), "fraction", basis="net"),
            "best_period": _ok(float(r.max()), "fraction/period"),
            "worst_period": _ok(float(r.min()), "fraction/period"),
            **dd,
        }
    )
    out.update(tail_metrics(r))
    return out


def tail_metrics(r: np.ndarray, level: float = 0.95) -> dict[str, Metric]:
    n = len(r)
    out: dict[str, Metric] = {}
    if n < 20:
        reason = f"n={n}<20"
        for k in (
            "var_loss_95",
            "expected_shortfall_95",
            "skewness",
            "excess_kurtosis",
            "tail_ratio",
        ):
            out[k] = _undef("", reason, "insufficient_data")
        return out
    loss = -r
    var = float(np.quantile(loss, level, method="linear"))
    tail = loss[loss >= var]
    m = r - r.mean()
    s2 = float(np.mean(m**2))
    out["var_loss_95"] = _ok(var, "fraction/period", quantile_method="linear", sign="loss>0")
    out["expected_shortfall_95"] = _ok(
        float(tail.mean()), "fraction/period", tail_observations=len(tail)
    )
    if s2 > 0:
        out["skewness"] = _ok(float(np.mean(m**3) / s2**1.5), "", estimator="g1 (biased)")
        out["excess_kurtosis"] = _ok(float(np.mean(m**4) / s2**2 - 3), "", estimator="g2")
    else:
        out["skewness"] = _undef("", "zero_dispersion")
        out["excess_kurtosis"] = _undef("", "zero_dispersion")
    hi, lo = np.quantile(r, 0.95), np.quantile(r, 0.05)
    out["tail_ratio"] = (
        _ok(float(hi / abs(lo)), "ratio")
        if lo < 0 < hi
        else _undef("ratio", "tail_signs_not_as_expected")
    )
    return out


def instrument_returns(bars: pd.DataFrame, instrument: str | None = None) -> pd.Series:
    """Close-to-close daily returns of one instrument in a market-bars frame.

    ``instrument`` may be omitted when the frame holds exactly one. With total-return
    adjusted bars this is the instrument's total return, comparable with net strategy
    returns (which are also close to close).
    """
    names = sorted(bars["instrument"].unique())
    if instrument is None:
        if len(names) != 1:
            raise ValueError(f"benchmark bundle holds {len(names)} instruments; name one")
        instrument = names[0]
    if instrument not in names:
        raise ValueError(f"benchmark instrument {instrument!r} not in bundle")
    close = bars.loc[bars["instrument"] == instrument].set_index("date")["close"].sort_index()
    return close.pct_change().dropna().rename(instrument)


def benchmark_metrics(
    returns: pd.Series,
    bench: pd.Series,
    annualization: int,
    risk_free_annual: float = 0.0,
    label: str = "universe_equal_weight_daily_rebalanced_gross",
) -> dict[str, Metric]:
    r, b = returns.align(bench.dropna(), join="inner")
    a = annualization
    if len(r) < 20:
        return {"benchmark": _undef("", "fewer_than_20_aligned_returns", "insufficient_data")}
    rf = period_rate(risk_free_annual, a)
    active = r - b
    te = float(active.std(ddof=1))
    x, y = (b - rf).to_numpy(), (r - rf).to_numpy()
    vx = float(np.var(x, ddof=1))
    out = {
        "benchmark_total_return": _ok(
            float(np.prod(1 + b) - 1),
            "fraction",
            benchmark=label,
            aligned_sessions=len(b),
        ),
        "tracking_error": _ok(te * math.sqrt(a), "fraction/year^0.5"),
        "information_ratio": (
            _ok(float(active.mean() / te * math.sqrt(a)), "ratio")
            if te > 1e-15
            else _undef("ratio", "zero_tracking_error")
        ),
        "correlation": (
            _ok(float(np.corrcoef(x, y)[0, 1]), "ratio")
            if vx > 1e-15 and np.std(y) > 1e-15
            else _undef("ratio", "zero_variance")
        ),
    }
    if vx > 1e-15:
        beta = float(np.cov(x, y, ddof=1)[0, 1] / vx)
        alpha = float(y.mean() - beta * x.mean())
        out["beta"] = _ok(beta, "ratio", model="OLS excess returns on benchmark")
        out["alpha_annual"] = _ok(alpha * a, "fraction/year", note="arithmetic, OLS intercept")
    else:
        out["beta"] = _undef("ratio", "zero_benchmark_variance")
    return out


# ---------------------------------------------------------------------------
# Trading and trade-episode metrics


def trading_metrics(result: BacktestResult, annualization: int) -> dict[str, Metric]:
    d = result.daily
    fills = result.trades[result.trades["status"] == "filled"]
    costs = {k: float(d[f"{k}_cost"].sum()) for k in (*COST_KINDS, "borrow")}
    gross = result.gross_returns.to_numpy()
    net = result.returns.to_numpy()
    traded = d["turnover"]
    return {
        **{f"total_{k}_cost": _ok(v, "currency") for k, v in costs.items()},
        "total_costs": _ok(sum(costs.values()), "currency"),
        "cost_drag_annual": _ok(
            float((gross.mean() - net.mean()) * annualization),
            "fraction/year",
            note="arithmetic mean gross minus net",
        ),
        "turnover_one_way_annual": _ok(
            float(0.5 * traded.mean() * annualization),
            "fraction of NAV/year",
            definition="0.5*traded/NAV",
        ),
        "average_gross_exposure": _ok(float(d["gross_exposure"].mean()), "fraction of NAV"),
        "average_net_exposure": _ok(float(d["net_exposure"].mean()), "fraction of NAV"),
        "max_gross_exposure": _ok(float(d["gross_exposure"].max()), "fraction of NAV"),
        "average_positions": _ok(float((d["n_long"] + d["n_short"]).mean()), "count"),
        "fills": _ok(len(fills), "count"),
        "rejected_orders": _ok(int((result.trades["status"] == "rejected").sum()), "count"),
        "participation_capped_fills": _ok(
            int((fills["reason"] == "participation_cap").sum()), "count"
        ),
        "max_participation": _ok(
            float(fills["participation"].max()) if fills["participation"].notna().any() else 0.0,
            "fraction of ADV",
        ),
        "total_financing": _ok(float(d["financing"].sum()), "currency"),
    }


def episode_metrics(episodes: pd.DataFrame, flat_tolerance: float) -> dict[str, Metric]:
    closed = episodes[episodes["status"] == "closed"]
    pnl = closed["pnl"].to_numpy(dtype=float)
    n = len(pnl)
    out: dict[str, Metric] = {
        "closed_trades": _ok(n, "count", definition="position episode (open to flat/flip)"),
        "open_trades": _ok(int((episodes["status"] == "open").sum()), "count"),
    }
    if n == 0:
        out["win_rate"] = _undef("fraction", "no_closed_trades")
        return out
    wins, losses = pnl[pnl > flat_tolerance], pnl[pnl < -flat_tolerance]
    flats = n - len(wins) - len(losses)
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    out.update(
        {
            "wins": _ok(len(wins), "count"),
            "losses": _ok(len(losses), "count"),
            "flats": _ok(flats, "count", tolerance=flat_tolerance),
            "win_rate": _ok(len(wins) / n, "fraction"),
            "non_flat_win_rate": (
                _ok(len(wins) / (len(wins) + len(losses)), "fraction")
                if len(wins) + len(losses)
                else _undef("fraction", "all_flat")
            ),
            "average_trade_pnl": _ok(float(pnl.mean()), "currency"),
            "median_trade_pnl": _ok(float(np.median(pnl)), "currency"),
            "average_win": (
                _ok(float(wins.mean()), "currency")
                if len(wins)
                else _undef("currency", "no_wins", "not_applicable")
            ),
            "average_loss": (
                _ok(float(losses.mean()), "currency")
                if len(losses)
                else _undef("currency", "no_losses", "not_applicable")
            ),
            "payoff_ratio": (
                _ok(float(wins.mean() / -losses.mean()), "ratio")
                if len(wins) and len(losses)
                else _undef("ratio", "no_wins_or_losses")
            ),
            "profit_factor": (
                _ok(gross_win / gross_loss, "ratio")
                if gross_loss > 0
                else _undef("ratio", "no_losing_trades")
            ),
            "expectancy": _ok(float(pnl.mean()), "currency", note="equals mean trade P&L"),
            "total_closed_trade_pnl": _ok(float(pnl.sum()), "currency"),
            "best_trade": _ok(float(pnl.max()), "currency"),
            "worst_trade": _ok(float(pnl.min()), "currency"),
            "average_holding_sessions": _ok(float(closed["holding_sessions"].mean()), "sessions"),
            "median_holding_sessions": _ok(float(closed["holding_sessions"].median()), "sessions"),
        }
    )
    for side in ("long", "short"):
        sub = closed[closed["side"] == side]["pnl"]
        if len(sub):
            out[f"{side}_trades"] = _ok(
                len(sub), "count", win_rate=float((sub > 0).mean()), total_pnl=float(sub.sum())
            )
    return out


def compute_metrics(
    result: BacktestResult,
    external_benchmark: pd.Series | None = None,
    external_label: str = "external",
) -> dict[str, dict[str, Any]]:
    """All metric sections. ``external_benchmark`` (daily returns, e.g. an index ETF)
    adds an ``external_benchmark`` section next to the universe equal-weight one."""
    cfg = result.config
    rets = result.returns
    net_profit = float(result.daily["equity"].iloc[-1] - cfg.initial_capital)
    sections = {
        "performance": {
            "net_profit": _ok(net_profit, "currency", external_flows=0),
            **return_metrics(
                rets,
                v0=cfg.initial_capital,
                annualization=cfg.annualization,
                risk_free_annual=cfg.risk_free_annual,
                mar_annual=cfg.mar_annual,
            ),
        },
        "gross_of_costs": {
            k: v
            for k, v in return_metrics(
                result.gross_returns,
                v0=cfg.initial_capital,
                annualization=cfg.annualization,
                risk_free_annual=cfg.risk_free_annual,
                mar_annual=cfg.mar_annual,
            ).items()
            if k in ("total_return", "cagr", "annual_volatility", "sharpe", "max_drawdown")
        },
        "benchmark": benchmark_metrics(
            rets, result.benchmark, cfg.annualization, cfg.risk_free_annual
        ),
        "trading": trading_metrics(result, cfg.annualization),
        "trades": episode_metrics(result.episodes, 1e-9 * cfg.initial_capital),
    }
    if external_benchmark is not None:
        sections["external_benchmark"] = benchmark_metrics(
            rets, external_benchmark, cfg.annualization, cfg.risk_free_annual, external_label
        )
    return {name: {k: m.to_dict() for k, m in sec.items()} for name, sec in sections.items()}
