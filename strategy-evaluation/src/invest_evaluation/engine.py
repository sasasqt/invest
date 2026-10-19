"""Daily event-driven backtest engine with explicit timing and cost accounting.

Event order within each session ``t``:

1. **Open.** Positions are marked from the previous mark to the open. Orders whose fill
   date is ``t`` execute at the open price; transaction costs are paid in cash.
2. **Close.** Positions are marked to the close. Explicit delisting settlements known at
   this close convert holdings to cash at the supplied settlement price. Missing bars
   alone never imply a delisting; holdings retain their last known mark. Borrow fees on
   shorts and interest on cash accrue.
3. **Decision.** On rebalance dates, scores dated ``t`` (available after the close of
   ``t``) are turned into target weights. They fill at the open of ``t + 1 + delay``.

So a decision can never use a price it trades at, and no signal is acted on before the
session after its decision date. Per-instrument P&L attribution (including costs) is kept
so equity, trade P&L and costs reconcile exactly; :class:`AccountingError` is raised if
they don't.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, NoReturn

import numpy as np
import pandas as pd

from invest_data.bundle import BundleError
from invest_data.pit import membership_panel
from invest_data.schemas import AS_TRADED_CLOSE, real_numbers
from invest_evaluation.config import BacktestConfig
from invest_evaluation.strategies import QuantileStrategy, Strategy

COST_KINDS = ("commission", "spread", "impact")
DECISION_COLS = ["decision_date", "instrument", "score", "weight"]


class AccountingError(RuntimeError):
    """Equity does not reconcile with attributed P&L and costs."""


class InputError(ValueError):
    """Market data or signals are inconsistent with the backtest contract."""


@dataclass
class BacktestResult:
    daily: pd.DataFrame  # one row per session
    trades: pd.DataFrame  # one row per fill (or rejected order)
    episodes: pd.DataFrame  # closed and open position episodes
    benchmark: pd.Series  # equal-weight universe daily return (gross, no costs)
    config: BacktestConfig
    warnings: list[str]
    # With ``record_decisions``: one row per eligible instrument per decision:
    # decision_date, instrument, score, weight (the target, 0 if not held). Records
    # decision-time eligibility and holdings; empty otherwise.
    decisions: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=DECISION_COLS))

    @property
    def returns(self) -> pd.Series:
        eq = self.daily["equity"]
        prev = eq.shift(1)
        prev.iloc[0] = self.config.initial_capital
        return (eq / prev - 1.0).rename("return")

    @property
    def gross_returns(self) -> pd.Series:
        eq = self.daily["equity_before_costs"]
        prev = eq.shift(1)
        prev.iloc[0] = self.config.initial_capital
        return (eq / prev - 1.0).rename("gross_return")


def check_price_rules(bars: pd.DataFrame, config: BacktestConfig) -> pd.Series | None:
    """``min_price`` compares the close as traded on the decision date.

    An adjusted close is rescaled by every later split and dividend, so comparing it with
    a price level would let later corporate actions decide earlier eligibility. A name
    whose as-traded close is unknown (null) on a decision date is not eligible then;
    :func:`run_backtest` also refuses a window with no known as-traded close. Returns the
    as-traded closes with unknown or invalid values as NaN, or None without a price floor.
    """
    if config.execution.min_price <= 0:
        return None
    if AS_TRADED_CLOSE.name not in bars:
        _no_traded_close(config, "these bars lack it")
    return _traded_closes(bars)


def _traded_closes(bars: pd.DataFrame) -> pd.Series:
    """The as-traded closes; only finite positive values count as known (others are NaN)."""
    try:
        values = real_numbers(bars[AS_TRADED_CLOSE.name], AS_TRADED_CLOSE.name)
    except BundleError as exc:
        raise InputError(str(exc)) from exc
    known = np.isfinite(values) & (values > 0)
    return pd.Series(np.where(known, values, np.nan), index=bars.index)


def _no_traded_close(config: BacktestConfig, why: str) -> NoReturn:
    raise InputError(
        f"execution.min_price {config.execution.min_price} needs the as-traded close "
        f"({AS_TRADED_CLOSE.name}), but {why}; adjusted closes depend on later splits and "
        "dividends. Publish bars with it, or set execution.min_price to 0"
    )


def _wide(bars: pd.DataFrame, field: str) -> pd.DataFrame:
    return bars.pivot(index="date", columns="instrument", values=field).sort_index()


def _delisting_events(
    events: pd.DataFrame | None, calendar: pd.Index, instruments: pd.Index
) -> dict[int, list[tuple[int, float]]]:
    """Validate cash settlements available at each event date's close."""
    if events is None or events.empty:
        return {}
    required = {"date", "instrument", "settlement_price"}
    if set(events.columns) != required or events.columns.has_duplicates:
        raise InputError("delistings require date, instrument, settlement_price columns")
    names = events["instrument"].astype(object)  # categorical inputs need a plain boolean mask
    if not names.map(lambda v: isinstance(v, str) and bool(v.strip())).all():
        raise InputError("delisting instrument must be a nonempty string")
    if events["instrument"].duplicated().any():
        raise InputError("only one delisting settlement per instrument is supported")
    out: dict[int, list[tuple[int, float]]] = {}
    for row in events.itertuples(index=False):
        try:
            date = pd.Timestamp(row.date)
        except (TypeError, ValueError) as exc:
            raise InputError("invalid delisting date") from exc
        if date not in calendar or row.instrument not in instruments:
            raise InputError("delisting date/instrument is not in the market calendar/universe")
        price = row.settlement_price
        if (
            isinstance(price, bool)
            or not isinstance(price, Real)
            or not math.isfinite(price)
            or price < 0
        ):
            raise InputError("delisting settlement_price must be finite and nonnegative")
        out.setdefault(int(calendar.get_loc(date)), []).append(
            (int(instruments.get_loc(row.instrument)), float(price))
        )
    return out


def _validated_weights(weights: pd.Series, eligible: pd.Index, gross_limit: float) -> pd.Series:
    if not isinstance(weights, pd.Series) or not weights.index.is_unique:
        raise InputError("strategy targets must be a Series with unique instrument identifiers")
    if not weights.index.isin(eligible).all():
        raise InputError("strategy targets include unknown or ineligible instruments")
    if (
        not pd.api.types.is_numeric_dtype(weights.dtype)
        or pd.api.types.is_bool_dtype(weights.dtype)
        or pd.api.types.is_complex_dtype(weights.dtype)
    ):
        raise InputError("strategy target weights must be finite numbers")
    values = weights.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise InputError("strategy target weights must be finite numbers")
    if np.abs(values).sum() > gross_limit + 1e-12:
        raise InputError("strategy targets exceed configured gross_leverage")
    return pd.Series(values, index=weights.index.copy())


def run_backtest(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: BacktestConfig | None = None,
    strategy: Strategy | None = None,
    universe: pd.DataFrame | None = None,
    delistings: pd.DataFrame | None = None,
    *,
    record_decisions: bool = False,
) -> BacktestResult:
    """Simulate ``signals`` on ``bars``. ``universe`` (a membership table) limits new
    positions to instruments that are members on the decision date; holdings that leave
    the universe are sold at the next rebalance. Optional ``delistings`` contains
    ``date, instrument, settlement_price`` cash events known at the event date's close.
    Missing bars retain the last mark; they never imply a liquidation.
    ``record_decisions`` fills ``BacktestResult.decisions`` (one row per eligible name
    per decision); it is off by default because only bucket reports need it."""
    cfg = config or BacktestConfig()
    known_traded = check_price_rules(bars, cfg)
    strat = strategy or QuantileStrategy(cfg.strategy)
    ex, cm = cfg.execution, cfg.costs
    warnings: list[str] = []

    open_w, close_w, vol_w = (_wide(bars, f) for f in ("open", "close", "volume"))
    calendar = close_w.index
    instruments = close_w.columns
    settlement_events = _delisting_events(delistings, calendar, instruments)
    if signals.duplicated(["decision_date", "instrument"]).any():
        raise InputError("duplicate (decision_date, instrument) signals")
    unknown_dates = set(signals["decision_date"]) - set(calendar)
    if unknown_dates:
        raise InputError(f"{len(unknown_dates)} signal dates are not market sessions")
    unknown_ids = set(signals["instrument"]) - set(instruments)
    if unknown_ids:
        raise InputError(f"signals for unknown instruments: {sorted(unknown_ids)[:5]}")
    scores = signals.pivot(index="decision_date", columns="instrument", values="score").reindex(
        index=calendar, columns=instruments
    )

    # Trailing liquidity/volatility estimates, known at each session's close.
    dollar_vol = close_w * vol_w
    adv = dollar_vol.rolling(cm.adv_window, min_periods=cm.adv_window).mean()
    daily_vol = (
        (close_w / close_w.shift(1) - 1).rolling(cm.vol_window, min_periods=cm.vol_window).std()
    )

    # Evaluation window: from `start` (default: the first session with any signal, so
    # periods before the strategy could act don't dilute its statistics) until `end`.
    mask = np.ones(len(calendar), dtype=bool)
    if cfg.start:
        mask &= calendar >= pd.Timestamp(cfg.start)
    else:
        has_signal = scores.notna().any(axis=1).to_numpy()
        if not has_signal.any():
            raise InputError("no signals fall on market sessions")
        mask[: int(np.argmax(has_signal))] = False
    if cfg.end:
        mask &= calendar <= pd.Timestamp(cfg.end)
    sessions = np.flatnonzero(mask)
    if len(sessions) < 2:
        raise InputError("evaluation window has fewer than two sessions")

    px_open, px_close = open_w.to_numpy(), close_w.to_numpy()
    # Price-level eligibility (zero min_price passes every name with a close).
    traded_close = None
    if known_traded is not None:
        as_traded = bars[["date", "instrument"]].assign(traded=known_traded)
        traded_close = (
            _wide(as_traded, "traded").reindex(index=calendar, columns=instruments).to_numpy()
        )
        if not np.isfinite(traded_close[sessions]).any():
            _no_traded_close(cfg, "no session in the evaluation window has a positive finite one")
    ADV, VOL, S = adv.to_numpy(), daily_vol.to_numpy(), scores.to_numpy()
    member = (
        membership_panel(universe, pd.DatetimeIndex(calendar), instruments).to_numpy()
        if universe is not None
        else np.ones((len(calendar), len(instruments)), dtype=bool)
    )
    n = len(instruments)
    unknown_traded_close = 0  # otherwise eligible names a price floor excluded for lack of a price
    missing_mark_warned = np.zeros(n, dtype=bool)
    retired = np.zeros(n, dtype=bool)
    for event_i, entries in settlement_events.items():
        if event_i < sessions[0]:
            for j, _ in entries:
                retired[j] = True

    shares = np.zeros(n)
    mark = np.full(n, np.nan)
    pnl = np.zeros(n)  # cumulative attributed P&L incl. costs, per instrument
    cash = cfg.initial_capital
    cum_costs = {k: 0.0 for k in (*COST_KINDS, "borrow")}
    cum_financing = 0.0
    pending: dict[int, tuple[int, pd.Series]] = {}
    ep_start = np.full(n, -1)
    ep_side = np.zeros(n)
    ep_pnl0 = np.zeros(n)
    episodes: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    decisions: list[pd.DataFrame] = []
    first_decision: int | None = None
    borrow_daily = cm.borrow_bps_annual / 1e4 / cfg.annualization
    cash_daily = cm.cash_rate_annual / cfg.annualization

    def close_episode(j: int, i: int, exit_pnl: float, reason: str) -> None:
        episodes.append(
            {
                "instrument": instruments[j],
                "side": "long" if ep_side[j] > 0 else "short",
                "entry_date": calendar[ep_start[j]],
                "exit_date": calendar[i],
                "holding_sessions": i - ep_start[j],
                "pnl": exit_pnl - ep_pnl0[j],
                "status": "closed",
                "exit_reason": reason,
            }
        )
        ep_start[j], ep_side[j] = -1, 0.0

    def open_episode(j: int, i: int, side: float, pnl_at_start: float) -> None:
        ep_start[j], ep_side[j], ep_pnl0[j] = i, side, pnl_at_start

    for i in sessions.tolist():
        date = calendar[i]
        day_costs = {k: 0.0 for k in (*COST_KINDS, "borrow")}
        traded = 0.0
        n_rejected = n_clipped = 0

        # 1. Open: mark to open, then execute orders scheduled for this session.
        has_open = ~np.isnan(px_open[i])
        held_open = has_open & (shares != 0)
        pnl[held_open] += shares[held_open] * (px_open[i][held_open] - mark[held_open])
        mark[has_open] = px_open[i][has_open]
        if i in pending:
            dec_i, weights = pending.pop(i)
            equity_open = cash + np.nansum(shares * mark)
            target = np.zeros(n)
            if len(weights):
                idx = instruments.get_indexer(weights.index)
                target[idx] = weights.to_numpy()
            for j in np.flatnonzero((target != 0) | (shares != 0)).tolist():
                if retired[j]:
                    trades.append(
                        {
                            "date": date,
                            "instrument": instruments[j],
                            "status": "rejected",
                            "reason": "delisted",
                            "decision_date": calendar[dec_i],
                        }
                    )
                    n_rejected += 1
                    continue
                want = target[j] * equity_open / px_open[i][j] if has_open[j] else np.nan
                if not has_open[j]:
                    trades.append(
                        {
                            "date": date,
                            "instrument": instruments[j],
                            "status": "rejected",
                            "reason": "no_bar_on_fill_date",
                            "decision_date": calendar[dec_i],
                        }
                    )
                    n_rejected += 1
                    continue
                delta = want - shares[j]
                if abs(delta) * px_open[i][j] < 1e-9 * equity_open:
                    continue
                adv_j, vol_j = ADV[dec_i][j], VOL[dec_i][j]
                if not (np.isfinite(adv_j) and adv_j > 0 and np.isfinite(vol_j)):
                    trades.append(
                        {
                            "date": date,
                            "instrument": instruments[j],
                            "status": "rejected",
                            "reason": "no_liquidity_estimate",
                            "decision_date": calendar[dec_i],
                        }
                    )
                    n_rejected += 1
                    continue
                cap = ex.max_participation * adv_j / px_open[i][j]
                clipped = abs(delta) > cap
                if clipped:
                    delta = np.sign(delta) * cap
                    n_clipped += 1
                notional = abs(delta) * px_open[i][j]
                c = {
                    "commission": notional * cm.commission_bps / 1e4,
                    "spread": notional * cm.half_spread_bps / 1e4,
                    "impact": notional * cm.impact_coef * vol_j * np.sqrt(notional / adv_j),
                }
                cost = sum(c.values())
                old, new = shares[j], shares[j] + delta
                # Allocate the trade's cost between closing and opening legs by quantity.
                closing_qty = abs(old) if (old != 0 and np.sign(new) != np.sign(old)) else 0.0
                close_share = closing_qty / abs(delta) if closing_qty else 0.0
                pnl[j] -= cost * close_share
                if closing_qty:
                    close_episode(j, i, pnl[j], "rebalance")
                pnl[j] -= cost * (1 - close_share)
                if new != 0 and np.sign(new) != np.sign(old):
                    open_episode(j, i, np.sign(new), pnl[j] + cost * (1 - close_share))
                cash -= delta * px_open[i][j] + cost
                shares[j] = new
                traded += notional
                for k in COST_KINDS:
                    day_costs[k] += c[k]
                trades.append(
                    {
                        "date": date,
                        "instrument": instruments[j],
                        "status": "filled",
                        "reason": "participation_cap" if clipped else None,
                        "decision_date": calendar[dec_i],
                        "shares": delta,
                        "price": px_open[i][j],
                        "notional": delta * px_open[i][j],
                        **c,
                        "participation": notional / adv_j,
                    }
                )

        # 2. Close: mark, delistings, borrow and cash interest.
        has_close = ~np.isnan(px_close[i])
        stale = ~has_close & (shares != 0) & ~missing_mark_warned
        for j in np.flatnonzero(stale).tolist():
            warnings.append(
                f"{instruments[j]} has no close on {date.date()}; retaining last known mark "
                "until a new price or explicit settlement is available"
            )
        missing_mark_warned[stale] = True
        held_close = has_close & (shares != 0)
        pnl[held_close] += shares[held_close] * (px_close[i][held_close] - mark[held_close])
        mark[has_close] = px_close[i][has_close]
        for j, settlement_price in settlement_events.get(i, []):
            retired[j] = True
            if shares[j] == 0:
                continue
            pnl[j] += shares[j] * (settlement_price - mark[j])
            mark[j] = settlement_price
            cash += shares[j] * settlement_price
            trades.append(
                {
                    "date": date,
                    "instrument": instruments[j],
                    "status": "filled",
                    "reason": "delisted_liquidation",
                    "decision_date": None,
                    "shares": -shares[j],
                    "price": settlement_price,
                    "notional": -shares[j] * settlement_price,
                    "commission": 0.0,
                    "spread": 0.0,
                    "impact": 0.0,
                    "participation": None,
                }
            )
            shares[j] = 0.0
            close_episode(j, i, pnl[j], "delisted")
            warnings.append(f"{instruments[j]} settled on {date.date()} at {settlement_price}")
        short = shares < 0
        borrow = float(-np.sum(shares[short] * mark[short])) * borrow_daily
        if borrow:
            pnl[short] -= -shares[short] * mark[short] * borrow_daily
            day_costs["borrow"] = borrow
        financing = cash * cash_daily
        cash += financing - borrow
        cum_financing += financing
        for k, v in day_costs.items():
            cum_costs[k] += v

        mv = shares * np.where(np.isnan(mark), 0.0, mark)
        equity = cash + float(mv.sum())
        if equity <= 0:
            warnings.append(f"insolvent on {date.date()}: equity {equity:.2f}")
        rows.append(
            {
                "date": date,
                "equity": equity,
                "cash": cash,
                "long_value": float(mv[mv > 0].sum()),
                "short_value": float(-mv[mv < 0].sum()),
                "n_long": int((shares > 0).sum()),
                "n_short": int((shares < 0).sum()),
                "traded_notional": traded,
                **{f"{k}_cost": v for k, v in day_costs.items()},
                "financing": financing,
                "n_rejected": n_rejected,
                "n_clipped": n_clipped,
                "cum_costs": sum(cum_costs.values()),
            }
        )
        if equity <= 0:
            break

        # 3. Decision after the close.
        if first_decision is None and np.isfinite(S[i]).any():
            first_decision = i
        if first_decision is not None and (i - first_decision) % cfg.strategy.rebalance_every == 0:
            fill_i = i + 1 + ex.delay
            if fill_i <= sessions[-1]:
                tradable = (
                    np.isfinite(S[i])
                    & member[i]
                    & ~retired
                    & has_close
                    & np.isfinite(ADV[i])
                    & (np.nan_to_num(ADV[i]) > ex.min_adv_dollar)
                )
                eligible = tradable
                if traded_close is not None:
                    unknown_traded_close += int((tradable & np.isnan(traded_close[i])).sum())
                    eligible = tradable & (traded_close[i] >= ex.min_price)
                sc = pd.Series(S[i][eligible], index=instruments[eligible], name="score")
                targets = _validated_weights(
                    strat.target_weights(sc), sc.index, cfg.strategy.gross_leverage
                )
                pending[fill_i] = (i, targets)
                if record_decisions:
                    decisions.append(
                        pd.DataFrame(
                            {
                                "decision_date": date,
                                "instrument": sc.index,
                                "score": sc.to_numpy(),
                                "weight": targets.reindex(sc.index, fill_value=0.0).to_numpy(),
                            },
                            columns=DECISION_COLS,
                        )
                    )

    if unknown_traded_close:
        warnings.append(
            f"{unknown_traded_close} otherwise eligible name-decisions had no positive finite "
            f"{AS_TRADED_CLOSE.name} and failed execution.min_price"
        )

    # Open episodes at the end are reported with unrealised P&L.
    end_i = sessions[0] + len(rows) - 1
    for j in np.flatnonzero(shares != 0).tolist():
        episodes.append(
            {
                "instrument": instruments[j],
                "side": "long" if shares[j] > 0 else "short",
                "entry_date": calendar[ep_start[j]],
                "exit_date": None,
                "holding_sessions": end_i - ep_start[j],
                "pnl": pnl[j] - ep_pnl0[j],
                "status": "open",
                "exit_reason": None,
            }
        )

    daily = pd.DataFrame(rows).set_index("date")
    # Gross of costs: each session's net return plus that session's trading and borrow
    # costs over the previous close's equity, compounded. Adding cumulative costs back to
    # equity instead would divide every later session's gross return by a pile of past
    # costs that earns nothing, understating gross returns and the cost drag.
    prev_equity = daily["equity"].shift(1).fillna(cfg.initial_capital)
    day_costs_paid = daily["cum_costs"].diff().fillna(daily["cum_costs"].iloc[0])
    gross_return = (daily["equity"] + day_costs_paid) / prev_equity - 1.0
    daily["equity_before_costs"] = cfg.initial_capital * (1.0 + gross_return).cumprod()
    daily["gross_exposure"] = (daily["long_value"] + daily["short_value"]) / daily["equity"]
    daily["net_exposure"] = (daily["long_value"] - daily["short_value"]) / daily["equity"]
    daily["turnover"] = daily["traded_notional"] / daily["equity"].shift(1).fillna(
        cfg.initial_capital
    )

    total = cfg.initial_capital + float(pnl.sum()) + cum_financing
    if not np.isclose(total, daily["equity"].iloc[-1], rtol=1e-9, atol=1e-6):
        raise AccountingError(
            f"equity {daily['equity'].iloc[-1]:.6f} != capital + attributed P&L {total:.6f}"
        )

    rets = close_w / close_w.shift(1) - 1
    held_from = np.vstack([member[:1], member[:-1]])  # members at the previous close
    # NaN on a session with no member return; benchmark metrics drop it rather than count 0%.
    bench = rets.where(held_from).mean(axis=1).reindex(daily.index).rename("benchmark")
    trade_cols = [
        "date",
        "instrument",
        "status",
        "reason",
        "decision_date",
        "shares",
        "price",
        "notional",
        *COST_KINDS,
        "participation",
    ]
    return BacktestResult(
        daily=daily,
        trades=pd.DataFrame(trades, columns=trade_cols),
        episodes=pd.DataFrame(
            episodes,
            columns=[
                "instrument",
                "side",
                "entry_date",
                "exit_date",
                "holding_sessions",
                "pnl",
                "status",
                "exit_reason",
            ],
        ),
        benchmark=bench,
        config=cfg,
        warnings=warnings,
        decisions=(
            pd.concat(decisions, ignore_index=True)
            if decisions
            else pd.DataFrame(columns=DECISION_COLS)
        ),
    )
