"""Executable decile and tail portfolios (QUANTILE-01).

Each bucket is backtested through the same engine, costs and timing as any other
strategy: long-only portfolios for every decile and for the top/bottom tail slices, and a
top-minus-bottom long-short portfolio per tail fraction. Bucket membership uses the
factor diagnostics' rule (average-rank percentiles, ties share a bucket), so a
portfolio holds exactly the names its diagnostic bucket describes, restricted to names
that are eligible at the decision date.

A bucket with fewer than ``min_names_per_bucket`` names on any decision that had a large
enough cross-section holds nothing on that decision and is reported as
``insufficient_data`` without performance figures, so a one-stock "1% tail" is never
presented as a diversified result. Tail slices overlap deciles and each other; they
are separate views, not a partition.
"""

from __future__ import annotations

import gzip
import json
import math
import os
from dataclasses import asdict, dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from invest_evaluation.config import BacktestConfig
from invest_evaluation.engine import run_backtest
from invest_evaluation.metrics import compute_metrics
from invest_evaluation.reporting import finite, write_json
from invest_evaluation.stats import bootstrap_ci
from invest_evaluation.strategies import BucketStrategy, Slice, bucket_numbers

# Version 2: buckets and tails are symmetric. The top tail is q <= f (counted from the top)
# instead of p > 1 - f, and the upper half of the buckets mirrors the lower half instead
# of ceil(p * n) throughout; both gave the top side up to one name more than the bottom.
QUANTILE_REPORT_VERSION = 2
TIE_RULE = (
    "average-rank percentile p in (0, 1] among decision-time eligible names, and q, the "
    "same percentile counted from the highest score; names with p <= q get bucket "
    "ceil(p * n) and the others n + 1 - ceil(q * n), so bucket 1 and bucket n mirror each "
    "other; bottom f holds p <= f; top f holds q <= f; tied scores share p and q and "
    "therefore a bucket"
)
PERFORMANCE_COLUMNS = (
    "net_cagr",
    "gross_cagr",
    "net_sharpe",
    "gross_sharpe",
    "net_sharpe_ci_low",
    "net_sharpe_ci_high",
    "max_drawdown",
    "turnover_one_way_annual",
    "cost_drag_annual",
    "total_costs",
)


@dataclass(frozen=True)
class QuantileConfig:
    """Which bucket portfolios to run and the small-sample rule, declared before the run."""

    n_buckets: int = 10
    tail_fractions: tuple[float, ...] = (0.01, 0.05, 0.1)
    min_names_per_bucket: int = 5

    def __post_init__(self) -> None:
        for name, minimum in (("n_buckets", 2), ("min_names_per_bucket", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        fractions = self.tail_fractions
        if isinstance(fractions, str) or not isinstance(fractions, list | tuple):
            raise ValueError("tail_fractions must be a list of fractions")
        for f in fractions:
            if isinstance(f, bool) or not isinstance(f, Real) or not math.isfinite(f):
                raise ValueError("tail fractions must be finite numbers")
            if not 0 < f <= 0.5:
                raise ValueError("tail fractions must be in (0, 0.5]")
        normalized = tuple(sorted(float(f) for f in fractions))
        if len(set(normalized)) != len(normalized):
            raise ValueError("tail fractions must be unique")
        object.__setattr__(self, "tail_fractions", normalized)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["tail_fractions"] = list(self.tail_fractions)
        return out


@dataclass(frozen=True)
class BucketPortfolio:
    name: str
    kind: str  # "bucket", "top", "bottom" (long-only) or "long_short"
    long: Slice
    short: Slice | None = None


def bucket_portfolios(qcfg: QuantileConfig) -> list[BucketPortfolio]:
    """Deciles (long-only), then per tail fraction: top, bottom, and top-minus-bottom."""
    n = qcfg.n_buckets
    out = [BucketPortfolio(f"q{k}", "bucket", Slice("bucket", k, n)) for k in range(1, n + 1)]
    for f in qcfg.tail_fractions:
        top, bottom = Slice("top", f, n), Slice("bottom", f, n)
        out += [
            BucketPortfolio(top.label, "top", top),
            BucketPortfolio(bottom.label, "bottom", bottom),
            BucketPortfolio(f"top_minus_bottom_{f}", "long_short", top, bottom),
        ]
    return out


MEMBERSHIP_KEYS = ["decision_date", "instrument", "score"]


def memberships(decisions: pd.DataFrame, n_buckets: int) -> pd.DataFrame:
    """Decision-time percentiles and bucket of every eligible name, from saved decisions.

    Tail membership follows from ``pct`` and ``pct_from_top`` with the documented rule,
    so one table serves every portfolio.
    """
    d = decisions[MEMBERSHIP_KEYS].copy()
    by_date = d.groupby("decision_date")["score"]
    # Grouped form of ``percentile_ranks``: average rank / names in the decision.
    d["pct"] = by_date.rank(method="average", pct=True)
    d["pct_from_top"] = by_date.rank(method="average", pct=True, ascending=False)
    d["bucket"] = bucket_numbers(d["pct"], d["pct_from_top"], n_buckets).astype(int)
    return d


def _leg_counts(member: pd.DataFrame, leg: Slice) -> pd.Series:
    # The same Slice.mask the strategy holds, so counts describe the held names.
    mask = leg.mask(member["pct"], member["pct_from_top"])
    return mask.groupby(member["decision_date"]).sum()


def _membership_for(
    member: pd.DataFrame | None, decisions: pd.DataFrame, n_buckets: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Membership table covering ``decisions`` and the (possibly longer) table to keep.

    Eligibility does not depend on holdings, so every portfolio sees the same decisions
    and only an insolvent portfolio stops early: each record is a prefix of the longest.
    Percentiles are computed once, from the longest record, and that assumption is checked.
    """

    def check_prefix(longer: pd.DataFrame, shorter: pd.DataFrame) -> None:
        same = all(
            np.array_equal(longer[c].to_numpy()[: len(shorter)], shorter[c].to_numpy())
            for c in MEMBERSHIP_KEYS
        )
        if not same:
            raise RuntimeError("bucket portfolios saw different decision-time eligible names")

    if member is None or len(decisions) > len(member):
        # Built from these decisions, so only an earlier record needs checking.
        previous, member = member, memberships(decisions, n_buckets)
        if previous is not None:
            check_prefix(member, previous)
    else:
        check_prefix(member, decisions)
    return member.iloc[: len(decisions)], member


def _value(section: dict[str, Any], key: str) -> float | None:
    metric = section.get(key, {})
    return metric.get("value") if metric.get("status") == "ok" else None


def _portfolio_row(
    p: BucketPortfolio,
    result: Any,
    member: pd.DataFrame,
    min_cross_section: int,
    qcfg: QuantileConfig,
) -> dict[str, Any]:
    sizes = member.groupby("decision_date").size()
    sized = sizes.index[sizes >= min_cross_section]
    legs = [p.long] if p.short is None else [p.long, p.short]
    counts = pd.concat(
        [_leg_counts(member, leg).reindex(sized, fill_value=0) for leg in legs], axis=1
    ).min(axis=1)
    insufficient = int((counts < qcfg.min_names_per_bucket).sum())
    row: dict[str, Any] = {
        "portfolio": p.name,
        "kind": p.kind,
        "long": p.long.label,
        "short": p.short.label if p.short else None,
        "decisions": len(sizes),
        "decisions_with_cross_section": len(sized),
        "insufficient_decisions": insufficient,
        "mean_names": float(counts.mean()) if len(counts) else None,
        "min_names": int(counts.min()) if len(counts) else None,
    }
    if not len(sized):
        row.update(status="insufficient_data", reason="no_decision_with_enough_eligible_names")
    elif insufficient:
        row.update(
            status="insufficient_data",
            reason=f"fewer_than_{qcfg.min_names_per_bucket}_names_on_"
            f"{insufficient}_of_{len(sized)}_decisions",
        )
    if "status" in row:
        return {**row, **dict.fromkeys(PERFORMANCE_COLUMNS)}

    cfg = result.config
    metrics = compute_metrics(result)
    perf, gross, trading = metrics["performance"], metrics["gross_of_costs"], metrics["trading"]
    ci = bootstrap_ci(result.returns, cfg.annualization, risk_free_annual=cfg.risk_free_annual)
    sharpe = perf["sharpe"]
    ci_bounds = ci.get("sharpe_ci") or [None, None]
    row.update(
        status="ok" if sharpe["status"] == "ok" else sharpe["status"],
        reason=None if sharpe["status"] == "ok" else sharpe["reason"],
        net_cagr=_value(perf, "cagr"),
        gross_cagr=_value(gross, "cagr"),
        net_sharpe=_value(perf, "sharpe"),
        gross_sharpe=_value(gross, "sharpe"),
        net_sharpe_ci_low=ci_bounds[0],
        net_sharpe_ci_high=ci_bounds[1],
        max_drawdown=_value(perf, "max_drawdown"),
        turnover_one_way_annual=_value(trading, "turnover_one_way_annual"),
        cost_drag_annual=_value(trading, "cost_drag_annual"),
        total_costs=_value(trading, "total_costs"),
    )
    return row


@dataclass
class QuantileResult:
    table: pd.DataFrame  # one row per portfolio
    returns: pd.DataFrame  # date x portfolio net daily returns
    memberships: pd.DataFrame  # decision_date, instrument, score, pct, pct_from_top, bucket
    warnings: dict[str, list[str]]
    config: BacktestConfig
    quantiles: QuantileConfig


def run_quantile_portfolios(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    config: BacktestConfig,
    qcfg: QuantileConfig,
    universe: pd.DataFrame | None = None,
    delistings: pd.DataFrame | None = None,
) -> QuantileResult:
    """Backtest every bucket portfolio with ``config``'s timing, costs and rebalancing.

    ``config.strategy.long_fraction``/``short_fraction`` are not used: the bucket defines
    the holdings. ``gross_leverage`` is the long-only exposure and is split evenly
    between legs for long-short portfolios, as in the quantile strategy.
    """
    s = config.strategy
    min_cross_section = max(s.min_names, qcfg.n_buckets)
    rows, returns, warnings = [], {}, {}
    member: pd.DataFrame | None = None
    for p in bucket_portfolios(qcfg):
        strategy = BucketStrategy(
            p.long,
            p.short,
            gross_leverage=s.gross_leverage,
            min_names=s.min_names,
            min_names_per_bucket=qcfg.min_names_per_bucket,
        )
        result = run_backtest(
            bars,
            signals,
            config,
            strategy,
            universe=universe,
            delistings=delistings,
            record_decisions=True,
        )
        current, member = _membership_for(member, result.decisions, qcfg.n_buckets)
        rows.append(_portfolio_row(p, result, current, min_cross_section, qcfg))
        returns[p.name] = result.returns
        warnings[p.name] = result.warnings
    assert member is not None
    return QuantileResult(
        table=pd.DataFrame(rows),
        returns=pd.DataFrame(returns),
        memberships=member,
        warnings=warnings,
        config=config,
        quantiles=qcfg,
    )


def save_quantile_run(
    out: str | os.PathLike[str], result: QuantileResult, provenance: dict[str, Any]
) -> Path:
    """Save tables, ``quantiles.json`` (versioned) and the manifest, then render the
    figure and ``report.md`` from the saved files only."""
    root = Path(out)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"run directory {root} is not empty")
    (root / "tables").mkdir(parents=True, exist_ok=True)
    (root / "figures").mkdir(exist_ok=True)
    table = result.table.astype(object).where(result.table.notna(), None)
    table.to_csv(root / "tables" / "portfolios.csv", index=False)
    result.returns.to_csv(root / "tables" / "daily_returns.csv.gz")
    with gzip.open(root / "tables" / "memberships.csv.gz", "wt", newline="") as fh:
        result.memberships.to_csv(fh, index=False)
    write_json(
        root / "config.json",
        finite({"backtest": result.config.to_dict(), "quantiles": result.quantiles.to_dict()}),
    )
    write_json(
        root / "quantiles.json",
        finite(
            {
                "report_version": QUANTILE_REPORT_VERSION,
                "kind": "quantile_portfolios",
                "settings": result.quantiles.to_dict(),
                "membership_rule": TIE_RULE,
                "min_cross_section": max(
                    result.config.strategy.min_names, result.quantiles.n_buckets
                ),
                "note": "Tail slices overlap deciles and each other; do not sum them.",
                "portfolios": table.to_dict("records"),
            }
        ),
    )
    write_json(root / "manifest.json", finite({**provenance, "warnings": result.warnings}))
    render_quantiles(root)
    return root


def _fmt(value: Any, pct: bool = False) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "–"
    return f"{value:.1%}" if pct else f"{value:.2f}"


def render_quantiles(root: Path) -> None:
    report = json.loads((root / "quantiles.json").read_text())
    table = pd.DataFrame(report["portfolios"])
    rets = pd.read_csv(root / "tables" / "daily_returns.csv.gz", index_col=0, parse_dates=True)

    deciles = table[table["kind"] == "bucket"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    x = np.arange(len(deciles))
    for offset, col, color, label in (
        (-0.2, "gross_cagr", "#7fa7d1", "before costs"),
        (0.2, "net_cagr", "#1f4e79", "net"),
    ):
        # A missing CAGR (insufficient or invalid portfolio) draws no bar, never a 0% one.
        values = pd.to_numeric(deciles[col], errors="coerce") * 100
        ax[0].bar(x + offset, values, width=0.38, color=color, label=label)
    for i, (cagr, status) in enumerate(zip(deciles["net_cagr"], deciles["status"], strict=True)):
        if pd.isna(pd.to_numeric(cagr, errors="coerce")):
            ax[0].text(i, 0, f" n/a ({status})", rotation=90, ha="center", va="bottom", fontsize=7)
    ax[0].set_xticks(x, deciles["portfolio"])
    ax[0].axhline(0, color="black", lw=0.6)
    ax[0].set_ylabel("CAGR (%)")
    ax[0].set_title("Long-only decile portfolios (q1 = lowest score; n/a = no CAGR)")
    ax[0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    # Insufficient portfolios held nothing on some decisions; their paths are not shown.
    spreads = table[(table["kind"] == "long_short") & (table["status"] == "ok")]
    shades = ("#1f4e79", "#5b8cc0", "#a9c4e2")
    for k, name in enumerate(reversed(spreads["portfolio"].tolist())):
        ax[1].plot(
            (1 + rets[name].fillna(0)).cumprod(),
            color=shades[min(k, len(shades) - 1)],
            lw=1.2,
            label=name,
        )
    skipped = table[(table["kind"] == "long_short") & (table["status"] != "ok")]
    if len(skipped):
        ax[1].text(
            0.01,
            0.01,
            "not shown: "
            + ", ".join(
                f"{p} ({s})" for p, s in zip(skipped["portfolio"], skipped["status"], strict=True)
            ),
            transform=ax[1].transAxes,
            fontsize=7,
            color="#555555",
        )
    ax[1].axhline(1, color="black", lw=0.6)
    ax[1].set_ylabel("growth of 1 (net)")
    ax[1].set_title("Top-minus-bottom long-short portfolios")
    if len(spreads):
        ax[1].legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(root / "figures" / "quantile_portfolios.png", dpi=120)
    plt.close(fig)

    s = report["settings"]
    lines = [
        "# Quantile portfolios",
        "",
        f"Report version {report['report_version']}. Each row is a separate backtest with the "
        "configured costs and timing. Membership: " + report["membership_rule"] + ".",
        "",
        f"Small-sample rule: a portfolio is `insufficient_data` when a leg held fewer than "
        f"{s['min_names_per_bucket']} names on any decision with at least "
        f"{report['min_cross_section']} eligible names; its performance is not reported. "
        + report["note"],
        "",
        "| portfolio | status | mean names | net CAGR | gross CAGR | net Sharpe "
        "| Sharpe 95% CI | max DD | turnover/yr | cost drag/yr |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["portfolios"]:
        ci = (
            f"[{_fmt(r['net_sharpe_ci_low'])}, {_fmt(r['net_sharpe_ci_high'])}]"
            if r["net_sharpe_ci_low"] is not None
            else "–"
        )
        lines.append(
            f"| {r['portfolio']} | {r['status']} | {_fmt(r['mean_names'])} "
            f"| {_fmt(r['net_cagr'], True)} | {_fmt(r['gross_cagr'], True)} "
            f"| {_fmt(r['net_sharpe'])} | {ci} | {_fmt(r['max_drawdown'], True)} "
            f"| {_fmt(r['turnover_one_way_annual'])} | {_fmt(r['cost_drag_annual'], True)} |"
        )
    lines += ["", "![quantile portfolios](figures/quantile_portfolios.png)", ""]
    (root / "report.md").write_text("\n".join(lines))
